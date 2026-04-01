from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
from scipy.spatial.distance import euclidean
import os
import json
import base64
from datetime import datetime
import threading

app = Flask(__name__, static_folder='templates', static_url_path='')
CORS(app)

# Load OpenCV's pre-trained Haar Cascade for face detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'  # Use /tmp for Vercel
KNOWN_FACES_FOLDER = '/tmp/known_faces'
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(KNOWN_FACES_FOLDER):
    os.makedirs(KNOWN_FACES_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Global variables for face recognition
known_faces = []  # Store face embeddings
known_names = []
is_training = False

def extract_face_embedding(image_path):
    """Extract face embedding from image using OpenCV Haar Cascade"""
    try:
        image = cv2.imread(image_path)
        if image is None:
            return None
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        if len(faces) > 0:
            # Get the largest face
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = largest_face
            
            # Extract face region
            face_crop = gray[y:y+h, x:x+w]
            
            # Create embedding from face region (histogram-based)
            hist = cv2.calcHist([face_crop], [0], None, [256], [0, 256])
            embedding = cv2.normalize(hist, hist).flatten()
            
            return embedding
        
        return None
    except Exception as e:
        print(f"Error extracting embedding: {e}")
        return None

def train_faces():
    """Load and train known faces from disk"""
    global known_faces, known_names, is_training
    
    if is_training:
        return
    
    is_training = True
    try:
        known_faces = []
        known_names = []
        
        if not os.path.exists(KNOWN_FACES_FOLDER):
            os.makedirs(KNOWN_FACES_FOLDER)
        
        for person_name in os.listdir(KNOWN_FACES_FOLDER):
            person_path = os.path.join(KNOWN_FACES_FOLDER, person_name)
            
            if os.path.isdir(person_path):
                for image_file in os.listdir(person_path):
                    image_path = os.path.join(person_path, image_file)
                    
                    if image_file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                        embedding = extract_face_embedding(image_path)
                        if embedding is not None:
                            known_faces.append(embedding)
                            known_names.append(person_name)
        
        print(f"✅ Training complete! Loaded {len(known_faces)} faces")
    except Exception as e:
        print(f"Error training faces: {e}")
    finally:
        is_training = False

@app.route('/')
def index():
    """Serve the main HTML page"""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"<h1>Error loading page</h1><p>{str(e)}</p>", 500

@app.route('/api/status')
def status():
    """API endpoint to get system status"""
    return jsonify({
        'status': 'running',
        'known_faces': len(known_faces),
        'known_names': len(set(known_names))
    })

@app.route('/api/train', methods=['POST'])
def train():
    """API endpoint to train face recognition system"""
    train_faces()
    return jsonify({
        'status': 'success',
        'message': 'Training complete',
        'faces_loaded': len(known_faces)
    })

@app.route('/api/upload-face', methods=['POST'])
def upload_face():
    """API endpoint to upload and save a face"""
    try:
        person_name = request.form.get('person_name')
        
        if not person_name:
            return jsonify({'error': 'person_name is required'}), 400
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Create person folder
        person_folder = os.path.join(KNOWN_FACES_FOLDER, person_name)
        if not os.path.exists(person_folder):
            os.makedirs(person_folder)
        
        # Save file
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(person_folder, filename)
        file.save(filepath)
        
        # Retrain
        train_faces()
        
        return jsonify({
            'status': 'success',
            'message': f'Face saved for {person_name}',
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-people')
def get_people():
    """API endpoint to get list of people"""
    try:
        people = {}
        if os.path.exists(KNOWN_FACES_FOLDER):
            for person_name in os.listdir(KNOWN_FACES_FOLDER):
                person_path = os.path.join(KNOWN_FACES_FOLDER, person_name)
                if os.path.isdir(person_path):
                    faces = [f for f in os.listdir(person_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))]
                    people[person_name] = len(faces)
        
        return jsonify({'people': people})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete-person/<person_name>', methods=['DELETE'])
def delete_person(person_name):
    """API endpoint to delete a person and their faces"""
    try:
        import shutil
        person_path = os.path.join(KNOWN_FACES_FOLDER, person_name)
        
        if os.path.exists(person_path):
            shutil.rmtree(person_path)
            train_faces()  # Retrain after deletion
            
            return jsonify({
                'status': 'success',
                'message': f'{person_name} deleted successfully'
            })
        
        return jsonify({'error': 'Person not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recognize-photo', methods=['POST'])
def recognize_photo():
    """API endpoint to recognize faces in uploaded photo"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Save uploaded file
        filename = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Detect and recognize faces
        image = cv2.imread(filepath)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        results = []
        for (x, y, w, h) in faces:
            face_crop = gray[y:y+h, x:x+w]
            hist = cv2.calcHist([face_crop], [0], None, [256], [0, 256])
            embedding = cv2.normalize(hist, hist).flatten()
            
            # Find closest match
            if len(known_faces) > 0:
                distances = [euclidean(embedding, known_face) for known_face in known_faces]
                min_distance = min(distances)
                min_index = distances.index(min_distance)
                
                # Threshold for recognition
                THRESHOLD = 50
                if min_distance < THRESHOLD:
                    name = known_names[min_index]
                    confidence = max(0, 100 - min_distance)
                else:
                    name = "Unknown"
                    confidence = 0
            else:
                name = "Unknown"
                confidence = 0
            
            results.append({
                'name': name,
                'confidence': confidence,
                'position': {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)}
            })
        
        # Cleanup
        try:
            os.remove(filepath)
        except:
            pass
        
        return jsonify({
            'status': 'success',
            'detected_count': len(faces),
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect-frame', methods=['POST'])
def detect_frame():
    """API endpoint to detect faces in video frames"""
    try:
        data = request.get_json()
        frame_data = data.get('frame')
        
        if not frame_data:
            return jsonify({'error': 'No frame data'}), 400
        
        # Decode base64 frame
        try:
            frame_bytes = base64.b64decode(frame_data.split(',')[1])
            nparr = np.frombuffer(frame_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except:
            return jsonify({'error': 'Invalid frame data'}), 400
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        detected_names = []
        unknown_count = 0
        
        for (x, y, w, h) in faces:
            face_crop = gray[y:y+h, x:x+w]
            hist = cv2.calcHist([face_crop], [0], None, [256], [0, 256])
            embedding = cv2.normalize(hist, hist).flatten()
            
            if len(known_faces) > 0:
                distances = [euclidean(embedding, known_face) for known_face in known_faces]
                min_distance = min(distances)
                min_index = distances.index(min_distance)
                
                THRESHOLD = 50
                if min_distance < THRESHOLD:
                    name = known_names[min_index]
                    detected_names.append(name)
                else:
                    unknown_count += 1
            else:
                unknown_count += 1
        
        return jsonify({
            'status': 'success',
            'detected_count': len(faces),
            'detected_names': list(set(detected_names)),
            'unknown_count': unknown_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def download_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # Train on startup
    train_faces()
    # Use PORT from environment (Vercel, Railway, etc) or default to 8000
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=False, host='0.0.0.0', port=port)
