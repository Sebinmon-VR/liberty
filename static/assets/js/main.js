/**
 * Main Javascript to handle Section Fetching
 */

async function loadSection(elementId, filePath) {
    try {
        const response = await fetch(filePath);
        if (!response.ok) {
            throw new Error(`Failed to load ${filePath}: ${response.statusText}`);
        }
        const htmlText = await response.text();
        const sectionContainer = document.getElementById(elementId);
        
        if (sectionContainer) {
            sectionContainer.innerHTML = htmlText;
            
            // Dispatch a custom event to re-initialize any JS meant for this section
            const event = new CustomEvent('sectionLoaded', { detail: { elementId, filePath } });
            document.dispatchEvent(event);
        }
    } catch (error) {
        console.error('Error fetching section:', error);
    }
}

async function initializeApp() {
    // Array of sections to load in order
    const sections = [
        { id: 'sec-hero', path: 'hero.html' },
        { id: 'sec-about', path: 'about.html' },
        { id: 'sec-booking', path: 'booking.html' },
        { id: 'sec-services', path: 'services.html' },
        { id: 'sec-info', path: 'info.html' },
        { id: 'sec-gallery', path: 'gallery.html' },
        { id: 'sec-footer', path: 'footer.html' }
    ];

    // Load them concurrently to speed up initial render, or sequentially if order of CSS loads matter.
    // Fetch API is async, so we can load them in parallel.
    const promises = sections.map(sec => loadSection(sec.id, sec.path));
    await Promise.all(promises);
    
    console.log("All sections loaded successfully.");
}

// Wait for DOM to be parsed before initiating fetch requests
document.addEventListener('DOMContentLoaded', initializeApp);
