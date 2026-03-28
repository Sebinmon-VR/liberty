import os
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'liberty_plus_secret_2026')

# Cosmos DB Configuration
ENDPOINT = os.environ.get('COSMOS_ENDPOINT')
KEY = os.environ.get('COSMOS_KEY')
DATABASE_ID = "liberty_bookings"
CONTAINER_SERVICES = "services"
CONTAINER_BOOKINGS = "bookings"
CONTAINER_ADMIN = "admins"
CONTAINER_SETTINGS = "settings"

client = CosmosClient(ENDPOINT, KEY)

# Ensure database and containers exist
try:
    db = client.create_database_if_not_exists(id=DATABASE_ID)
    PK_PATH = PartitionKey(path="/_partitionKey")
    
    services_container = db.create_container_if_not_exists(id=CONTAINER_SERVICES, partition_key=PK_PATH)
    bookings_container = db.create_container_if_not_exists(id=CONTAINER_BOOKINGS, partition_key=PK_PATH)
    admin_container = db.create_container_if_not_exists(id=CONTAINER_ADMIN, partition_key=PK_PATH)
    settings_container = db.create_container_if_not_exists(id=CONTAINER_SETTINGS, partition_key=PK_PATH)
    
    # Pre-populate default timings if settings container is empty
    try:
        query = "SELECT * FROM c WHERE c.id = 'timings'"
        items = list(settings_container.query_items(query=query, enable_cross_partition_query=True))
        if not items:
            default_timings = [
                "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
                "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
                "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM",
                "05:00 PM - 06:00 PM", "06:00 PM - 07:00 PM", "07:00 PM - 08:00 PM"
            ]
            settings_container.upsert_item({
                "id": "timings",
                "slots": default_timings,
                "_partitionKey": "global"
            })
    except Exception as e:
        print(f"Timing initialization error: {e}")

except exceptions.CosmosHttpResponseError as e:
    print(f"Cosmos DB Error: {e.message}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/services', methods=['GET'])
def get_services():
    try:
        items = list(services_container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True))
        return jsonify(items)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/settings/timings', methods=['GET'])
def get_timings():
    try:
        items = list(settings_container.query_items(query="SELECT * FROM c WHERE c.id = 'timings'", enable_cross_partition_query=True))
        if items: return jsonify(items[0]['slots'])
        return jsonify([])
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/bookings', methods=['POST'])
def save_booking():
    try:
        data = request.json
        if not all(k in data for k in ['fullName', 'phone', 'vehicleType', 'serviceType', 'preferredDate', 'preferredTime']):
            return jsonify({"error": "All fields are required"}), 400
        data['id'] = str(uuid.uuid4())
        data['createdAt'] = datetime.utcnow().isoformat()
        data['status'] = 'pending'
        bookings_container.create_item(body=data)
        return jsonify({"message": "Booking successful", "id": data['id']}), 201
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        try:
            query = f"SELECT * FROM c WHERE c.username = '{username}' AND c.password = '{password}'"
            items = list(admin_container.query_items(query=query, enable_cross_partition_query=True))
            if items:
                session['admin_logged_in'], session['admin_username'] = True, username
                return redirect(url_for('admin_dashboard'))
            flash('Invalid credentials', 'error')
        except Exception as e: flash(f"Login error: {e}", 'error')
    return render_template('login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    try:
        bookings = list(bookings_container.query_items(query="SELECT * FROM c ORDER BY c.createdAt DESC", enable_cross_partition_query=True))
        services = list(services_container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True))
        admins = list(admin_container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True))
        
        timing_item = list(settings_container.query_items(query="SELECT * FROM c WHERE c.id = 'timings'", enable_cross_partition_query=True))
        timings = timing_item[0]['slots'] if timing_item else []
        
        stats = {"total": len(bookings), "pending": len([b for b in bookings if b.get('status') == 'pending']), "done": len([b for b in bookings if b.get('status') == 'done']), "revenue": sum([float(b.get('totalCost', 0)) for b in bookings if b.get('status') == 'done'])}
        return render_template('admin.html', bookings=bookings, services=services, admins=admins, timings=timings, stats=stats)
    except Exception as e:
        flash(f"Error fetching data: {e}", 'error')
        return render_template('admin.html', bookings=[], services=[], admins=[], timings=[], stats={"total":0,"pending":0,"done":0,"revenue":0})

@app.route('/api/admin/bookings/<id>/status', methods=['PATCH'])
def update_booking_status(id):
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        status = request.json.get('status')
        items = list(bookings_container.query_items(query=f"SELECT * FROM c WHERE c.id = '{id}'", enable_cross_partition_query=True))
        if items:
            item = items[0]
            item['status'], item['updatedAt'] = status, datetime.utcnow().isoformat()
            bookings_container.upsert_item(body=item)
            return jsonify({"message": f"Booking marked as {status}"}), 200
        return jsonify({"error": "Not found"}), 404
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/settings/timings', methods=['POST'])
def update_timings():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        slots = request.json.get('slots', [])
        settings_container.upsert_item({
            "id": "timings",
            "slots": slots,
            "_partitionKey": "global"
        })
        return jsonify({"message": "Timings updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# Route for Admin Manual Booking
@app.route('/api/admin/bookings', methods=['POST'])
def admin_manual_booking():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    return save_booking()

@app.route('/api/admin/services', methods=['POST'])
def update_service():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        if not data.get('id'): data['id'] = str(uuid.uuid4())
        services_container.upsert_item(body=data)
        return jsonify({"message": "Service updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/services/<id>', methods=['DELETE'])
def delete_service(id):
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        items = list(services_container.query_items(query=f"SELECT * FROM c WHERE c.id = '{id}'", enable_cross_partition_query=True))
        if items:
            services_container.delete_item(item=id, partition_key=items[0].get('_partitionKey'))
            return jsonify({"message": "Service deleted"}), 200
        return jsonify({"error": "Not found"}), 404
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/admins', methods=['POST'])
def update_admin():
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        if not data.get('id'): data['id'] = str(uuid.uuid4())
        admin_container.upsert_item(body=data)
        return jsonify({"message": "Admin updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/admins/<id>', methods=['DELETE'])
def delete_admin(id):
    if not session.get('admin_logged_in'): return jsonify({"error": "Unauthorized"}), 401
    try:
        items = list(admin_container.query_items(query=f"SELECT * FROM c WHERE c.id = '{id}'", enable_cross_partition_query=True))
        if items:
            admin_container.delete_item(item=id, partition_key=items[0].get('_partitionKey'))
            return jsonify({"message": "Admin deleted"}), 200
        return jsonify({"error": "Not found"}), 404
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

if __name__ == '__main__': app.run(debug=True, port=5000)
