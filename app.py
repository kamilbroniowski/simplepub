from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort, jsonify
import os
import zipfile
import shutil
import json
import xml.etree.ElementTree as ET
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['EXTRACTED_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extracted')
app.config['USER_PREFS_FILE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_prefs.json')
app.config['PROGRESS_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'progress')
app.config['ALLOWED_EXTENSIONS'] = {'epub'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create necessary directories if they don't exist
for folder in [app.config['UPLOAD_FOLDER'], app.config['EXTRACTED_FOLDER'], app.config['PROGRESS_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Initialize user preferences if they don't exist
if not os.path.exists(app.config['USER_PREFS_FILE']):
    with open(app.config['USER_PREFS_FILE'], 'w') as f:
        json.dump({
            'font_size': 16,
            'font_family': 'serif',
            'line_height': 1.5,
            'theme': 'light'
        }, f)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_user_prefs():
    with open(app.config['USER_PREFS_FILE'], 'r') as f:
        return json.load(f)

def save_user_prefs(prefs):
    with open(app.config['USER_PREFS_FILE'], 'w') as f:
        json.dump(prefs, f)

def get_book_progress(book_id):
    progress_file = os.path.join(app.config['PROGRESS_FOLDER'], f"{book_id}.json")
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {'current_file': None, 'position': 0}

def save_book_progress(book_id, progress_data):
    progress_file = os.path.join(app.config['PROGRESS_FOLDER'], f"{book_id}.json")
    with open(progress_file, 'w') as f:
        json.dump(progress_data, f)

def extract_epub(epub_path, extract_to):
    """Extract the EPUB file (which is a ZIP archive) to a directory"""
    with zipfile.ZipFile(epub_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def parse_epub_metadata(extract_path):
    """Parse the EPUB metadata to get book information and reading order"""
    # Find the container.xml file
    container_path = os.path.join(extract_path, 'META-INF', 'container.xml')
    if not os.path.exists(container_path):
        return None, []
    
    # Parse container.xml to find the OPF file
    tree = ET.parse(container_path)
    root = tree.getroot()
    
    # Find the rootfile element which points to the OPF file
    rootfile_element = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
    if rootfile_element is None:
        return None, []
    
    opf_path = rootfile_element.get('full-path')
    opf_full_path = os.path.join(extract_path, opf_path)
    opf_dir = os.path.dirname(opf_full_path)
    
    if not os.path.exists(opf_full_path):
        return None, []
    
    # Parse the OPF file
    opf_tree = ET.parse(opf_full_path)
    opf_root = opf_tree.getroot()
    
    # Get book metadata
    metadata = {}
    metadata_elem = opf_root.find('.//{http://www.idpf.org/2007/opf}metadata')
    if metadata_elem is not None:
        # Get title
        title_elem = metadata_elem.find('.//{http://purl.org/dc/elements/1.1/}title')
        if title_elem is not None:
            metadata['title'] = title_elem.text
        
        # Get author
        creator_elem = metadata_elem.find('.//{http://purl.org/dc/elements/1.1/}creator')
        if creator_elem is not None:
            metadata['author'] = creator_elem.text
    
    # Get spine (reading order)
    spine = []
    spine_elem = opf_root.find('.//{http://www.idpf.org/2007/opf}spine')
    manifest_elem = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')
    
    if spine_elem is not None and manifest_elem is not None:
        # Get all items from manifest
        manifest_items = {}
        for item in manifest_elem.findall('.//{http://www.idpf.org/2007/opf}item'):
            item_id = item.get('id')
            item_href = item.get('href')
            if item_id and item_href:
                manifest_items[item_id] = item_href
        
        # Get reading order from spine
        for itemref in spine_elem.findall('.//{http://www.idpf.org/2007/opf}itemref'):
            idref = itemref.get('idref')
            if idref in manifest_items:
                # Add the full path to the content file
                content_path = os.path.join(os.path.dirname(opf_path), manifest_items[idref])
                spine.append(content_path)
    
    # Get TOC (table of contents)
    toc = []
    # First, try to find NCX file in manifest
    ncx_id = None
    if spine_elem is not None:
        ncx_id = spine_elem.get('toc')
    
    if not ncx_id and manifest_elem is not None:
        # Try to find item with NCX media type
        for item in manifest_elem.findall('.//{http://www.idpf.org/2007/opf}item'):
            if item.get('media-type') == 'application/x-dtbncx+xml':
                ncx_id = item.get('id')
                break
    
    if ncx_id and ncx_id in manifest_items:
        ncx_path = os.path.join(extract_path, os.path.dirname(opf_path), manifest_items[ncx_id])
        if os.path.exists(ncx_path):
            # Parse NCX file to get TOC
            ncx_tree = ET.parse(ncx_path)
            ncx_root = ncx_tree.getroot()
            
            nav_points = ncx_root.findall('.//{http://www.daisy.org/z3986/2005/ncx/}navPoint')
            for nav_point in nav_points:
                nav_label = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}navLabel')
                content = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}content')
                
                if nav_label is not None and content is not None:
                    text = nav_label.find('.//{http://www.daisy.org/z3986/2005/ncx/}text')
                    if text is not None and content.get('src'):
                        toc.append({
                            'title': text.text,
                            'href': os.path.join(os.path.dirname(opf_path), content.get('src'))
                        })
    
    return metadata, spine, toc, opf_dir

@app.route('/')
def index():
    """Display the library view with uploaded books"""
    books = []
    
    # Get all extracted books
    if os.path.exists(app.config['EXTRACTED_FOLDER']):
        for book_id in os.listdir(app.config['EXTRACTED_FOLDER']):
            book_path = os.path.join(app.config['EXTRACTED_FOLDER'], book_id)
            
            # Try to get book metadata
            metadata_file = os.path.join(book_path, 'metadata.json')
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    
                    # Get progress
                    progress = get_book_progress(book_id)
                    position_percent = 0
                    if 'spine_length' in metadata and metadata['spine_length'] > 0:
                        # Calculate percentage based on current spine position
                        if progress['current_file'] in metadata.get('spine_positions', {}):
                            position_index = metadata['spine_positions'][progress['current_file']]
                            position_percent = (position_index / metadata['spine_length']) * 100
                    
                    books.append({
                        'id': book_id,
                        'title': metadata.get('title', 'Unknown Title'),
                        'author': metadata.get('author', 'Unknown Author'),
                        'progress': round(position_percent)
                    })
    
    return render_template('index.html', books=books)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload for EPUB files"""
    if 'file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        # Generate a unique ID for the book
        book_id = str(uuid.uuid4())
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(upload_path)
        
        # Create extraction directory
        extract_path = os.path.join(app.config['EXTRACTED_FOLDER'], book_id)
        os.makedirs(extract_path, exist_ok=True)
        
        # Extract the EPUB file
        extract_epub(upload_path, extract_path)
        
        # Parse EPUB metadata
        metadata, spine, toc, opf_dir = parse_epub_metadata(extract_path)
        
        if metadata:
            # Save metadata and spine information for later use
            spine_positions = {file_path: i for i, file_path in enumerate(spine)}
            metadata_to_save = {
                'title': metadata.get('title', 'Unknown Title'),
                'author': metadata.get('author', 'Unknown Author'),
                'spine': spine,
                'spine_length': len(spine),
                'spine_positions': spine_positions,
                'toc': toc,
                'opf_dir': opf_dir
            }
            
            with open(os.path.join(extract_path, 'metadata.json'), 'w') as f:
                json.dump(metadata_to_save, f)
            
            # Initialize reading progress
            if spine:
                save_book_progress(book_id, {'current_file': spine[0], 'position': 0})
        
        # Remove the uploaded file to save space
        os.remove(upload_path)
        
        return redirect(url_for('index'))
    
    return redirect(url_for('index'))

@app.route('/read/<book_id>')
def read_book(book_id):
    """Display the book reader interface"""
    book_path = os.path.join(app.config['EXTRACTED_FOLDER'], book_id)
    
    if not os.path.exists(book_path):
        abort(404)
    
    # Load book metadata
    metadata_file = os.path.join(book_path, 'metadata.json')
    if not os.path.exists(metadata_file):
        abort(404)
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    # Get current progress
    progress = get_book_progress(book_id)
    
    # If no current file is set, use the first spine item
    if not progress['current_file'] and metadata['spine']:
        progress['current_file'] = metadata['spine'][0]
        save_book_progress(book_id, progress)
    
    # Get user preferences
    user_prefs = get_user_prefs()
    
    return render_template('reader.html', 
                          book_id=book_id, 
                          metadata=metadata, 
                          current_file=progress['current_file'],
                          position=progress['position'],
                          user_prefs=user_prefs)

@app.route('/book/<book_id>/content/<path:content_path>')
def book_content(book_id, content_path):
    """Serve the book content files (HTML, CSS, images)"""
    book_path = os.path.join(app.config['EXTRACTED_FOLDER'], book_id)
    
    if not os.path.exists(book_path):
        abort(404)
    
    # Load book metadata to get opf_dir
    metadata_file = os.path.join(book_path, 'metadata.json')
    if not os.path.exists(metadata_file):
        abort(404)
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    # Normalize content path (remove any URL parameters)
    if '#' in content_path:
        content_path = content_path.split('#')[0]
    
    # Calculate the absolute path to the content file
    abs_content_path = os.path.join(book_path, content_path)
    
    # Check if the file exists
    if not os.path.exists(abs_content_path) or not os.path.isfile(abs_content_path):
        abort(404)
    
    # Directory containing the requested content file
    content_dir = os.path.dirname(abs_content_path)
    content_filename = os.path.basename(abs_content_path)
    
    return send_from_directory(content_dir, content_filename)

@app.route('/api/save_progress', methods=['POST'])
def save_progress():
    """Save reading progress for a book"""
    data = request.json
    book_id = data.get('book_id')
    current_file = data.get('current_file')
    position = data.get('position', 0)
    
    if not book_id or not current_file:
        return jsonify({'success': False}), 400
    
    save_book_progress(book_id, {
        'current_file': current_file,
        'position': position
    })
    
    return jsonify({'success': True})

@app.route('/api/user_prefs', methods=['GET', 'PUT'])
def user_preferences():
    """Get or update user preferences"""
    if request.method == 'GET':
        return jsonify(get_user_prefs())
    
    elif request.method == 'PUT':
        data = request.json
        current_prefs = get_user_prefs()
        
        # Update preferences with new values
        for key in ['font_size', 'font_family', 'line_height', 'theme']:
            if key in data:
                current_prefs[key] = data[key]
        
        save_user_prefs(current_prefs)
        return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)
