import os
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv

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

client = CosmosClient(ENDPOINT, KEY)

# Ensure database and containers exist
try:
    db = client.create_database_if_not_exists(id=DATABASE_ID)
    services_container = db.create_container_if_not_exists(
        id=CONTAINER_SERVICES, 
        partition_key=PartitionKey(path="/vehicleType")
    )
    bookings_container = db.create_container_if_not_exists(
        id=CONTAINER_BOOKINGS, 
        partition_key=PartitionKey(path="/phone")
    )
    admin_container = db.create_container_if_not_exists(
        id=CONTAINER_ADMIN, 
        partition_key=PartitionKey(path="/username")
    )
    
    # Initialize a default admin if none exist
    try:
        query = "SELECT * FROM c WHERE c.username = 'admin'"
        items = list(admin_container.query_items(query=query, enable_cross_partition_query=True))
        if not items:
            admin_container.upsert_item({
                "id": str(uuid.uuid4()),
                "username": "admin",
                "password": "admin123"  # In production, use hashed passwords
            })
    except Exception as e:
        print(f"Error checking/seeding admin: {e}")

except exceptions.CosmosHttpResponseError as e:
    print(f"Cosmos DB Error: {e.message}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/services', methods=['GET'])
def get_services():
    try:
        query = "SELECT * FROM c"
        items = list(services_container.query_items(query=query, enable_cross_partition_query=True))
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings', methods=['POST'])
def save_booking():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        booking_id = str(uuid.uuid4())
        data['id'] = booking_id
        # Add timestamp
        from datetime import datetime
        data['createdAt'] = datetime.utcnow().isoformat()
        
        bookings_container.create_item(body=data)
        return jsonify({"message": "Booking successful", "id": booking_id}), 201
    except Exception as e:
        print(f"Booking Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            query = f"SELECT * FROM c WHERE c.username = '{username}' AND c.password = '{password}'"
            items = list(admin_container.query_items(query=query, enable_cross_partition_query=True))
            
            if items:
                session['admin_logged_in'] = True
                session['admin_username'] = username
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid credentials', 'error')
        except Exception as e:
            flash(f"Login error: {e}", 'error')
            
    return render_template('login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    try:
        query = "SELECT * FROM c ORDER BY c.createdAt DESC"
        bookings = list(bookings_container.query_items(query=query, enable_cross_partition_query=True))
        
        # Also fetch services for management
        query_services = "SELECT * FROM c"
        services = list(services_container.query_items(query=query_services, enable_cross_partition_query=True))
        return render_template('admin.html', bookings=bookings, services=services)
    except Exception as e:
        flash(f"Error fetching data: {e}", 'error')
        return render_template('admin.html', bookings=[], services=[])

@app.route('/api/admin/services', methods=['POST'])
def update_service():
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data"}), 400
            
        vehicle_type = data.get('vehicleType')
        if not vehicle_type:
            return jsonify({"error": "Vehicle Type is required"}), 400
            
        # If no ID, it's a new vehicle. Check if vehicleType already exists.
        if not data.get('id'):
            query = f"SELECT * FROM c WHERE c.vehicleType = '{vehicle_type}'"
            items = list(services_container.query_items(query=query, enable_cross_partition_query=True))
            if items:
                # Update existing
                data['id'] = items[0]['id']
            else:
                data['id'] = str(uuid.uuid4())
                
        services_container.upsert_item(body=data)
        return jsonify({"message": "Service updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/services/<id>', methods=['DELETE'])
def delete_service(id):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # We need the partition key (vehicleType) to delete. 
        # First fetch the item to get the vehicleType.
        item = services_container.read_item(item=id, partition_key=None) # This might not work if partition key is required.
        # Better: use query to find it.
        query = f"SELECT * FROM c WHERE c.id = '{id}'"
        items = list(services_container.query_items(query=query, enable_cross_partition_query=True))
        if items:
            services_container.delete_item(item=id, partition_key=items[0]['vehicleType'])
            return jsonify({"message": "Service deleted"}), 200
        else:
            return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
