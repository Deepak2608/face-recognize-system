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

app = Flask(__name__)
CORS(app)

# Load OpenCV's pre-trained Haar Cascade for face detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Configuration
UPLOAD_FOLDER = 'uploads'
KNOWN_FACES_FOLDER = 'known_faces'
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
    """Train the system with known faces"""
    global known_faces, known_names, is_training
    is_training = True
    known_faces = []
    known_names = []
    
    try:
        for person_name in os.listdir(KNOWN_FACES_FOLDER):
            person_folder = os.path.join(KNOWN_FACES_FOLDER, person_name)
            if not os.path.isdir(person_folder):
                continue
            
            for image_name in os.listdir(person_folder):
                if not image_name.lower().endswith(('.jpg', '.png', '.jpeg')):
                    continue
                    
                image_path = os.path.join(person_folder, image_name)
                try:
                    embedding = extract_face_embedding(image_path)
                    if embedding is not None:
                        known_faces.append(embedding)
                        known_names.append(person_name)
                except Exception as e:
                    print(f"Error loading {image_path}: {e}")
        
        is_training = False
        print(f"✅ Training complete! Loaded {len(known_faces)} faces")
    except Exception as e:
        is_training = False
        print(f"Error during training: {e}")

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/status')
def status():
    """Get system status"""
    return jsonify({
        'status': 'ready',
        'known_faces_count': len(known_faces),
        'is_training': is_training
    })

@app.route('/api/train', methods=['POST'])
def train():
    """Train the system"""
    if is_training:
        return jsonify({'error': 'Already training'}), 400
    
    thread = threading.Thread(target=train_faces)
    thread.start()
    
    return jsonify({
        'message': 'Training started',
        'known_faces_count': len(known_faces)
    })

@app.route('/api/upload-face', methods=['POST'])
def upload_face():
    """Upload a face image for a person"""
    try:
        person_name = request.form.get('person_name')
        if not person_name:
            return jsonify({'error': 'Person name required'}), 400
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Create person folder
        person_folder = os.path.join(KNOWN_FACES_FOLDER, person_name)
        os.makedirs(person_folder, exist_ok=True)
        
        # Save file
        filename = f"{person_name}_{len(os.listdir(person_folder))}.jpg"
        filepath = os.path.join(person_folder, filename)
        file.save(filepath)
        
        return jsonify({
            'message': 'Face uploaded successfully',
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recognize-photo', methods=['POST'])
def recognize_photo():
    """Recognize faces in uploaded photo"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Save temporary file
        temp_path = os.path.join(UPLOAD_FOLDER, 'temp.jpg')
        file.save(temp_path)
        
        # Load and process image
        image = cv2.imread(temp_path)
        if image is None:
            return jsonify({'error': 'Invalid image file'}), 400
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        results_list = []
        
        for (x, y, w, h) in faces:
            face_crop = gray[y:y+h, x:x+w]
            
            # Create embedding
            hist = cv2.calcHist([face_crop], [0], None, [256], [0, 256])
            embedding = cv2.normalize(hist, hist).flatten()
            
            name = "Unknown"
            confidence = 0
            
            if len(known_faces) > 0:
                # Compare with known faces
                distances = [euclidean(embedding, known_face) for known_face in known_faces]
                best_match_index = np.argmin(distances)
                best_distance = distances[best_match_index]
                
                # Normalize distance to confidence (lower distance = higher confidence)
                if best_distance < 5.0:  # Threshold for match
                    name = known_names[best_match_index]
                    confidence = max(0, 100 - (best_distance * 10))
            
            results_list.append({
                'name': name,
                'confidence': round(confidence, 2),
                'location': {
                    'top': int(y),
                    'right': int(x + w),
                    'bottom': int(y + h),
                    'left': int(x)
                }
            })
        
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return jsonify({
            'faces_found': len(results_list),
            'results': results_list
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect-frame', methods=['POST'])
def detect_frame():
    """Real-time face detection from video frame"""
    try:
        data = request.get_json()
        if not data or 'frame' not in data:
            return jsonify({'success': False, 'error': 'No frame provided'}), 400
        
        # Decode base64 frame
        import base64
        frame_data = data['frame'].split(',')[1] if ',' in data['frame'] else data['frame']
        frame_bytes = base64.b64decode(frame_data)
        
        # Convert to numpy array
        nparr = np.frombuffer(frame_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'success': False, 'error': 'Invalid frame'}), 400
        
        # Detect faces
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        detections = []
        
        for (x, y, w, h) in faces:
            face_crop = gray[y:y+h, x:x+w]
            
            # Create embedding
            hist = cv2.calcHist([face_crop], [0], None, [256], [0, 256])
            embedding = cv2.normalize(hist, hist).flatten()
            
            name = "Unknown"
            confidence = 0
            
            if len(known_faces) > 0:
                # Compare with known faces
                distances = [euclidean(embedding, known_face) for known_face in known_faces]
                best_match_index = np.argmin(distances)
                best_distance = distances[best_match_index]
                
                # Normalize distance to confidence
                if best_distance < 5.0:  # Threshold for match
                    name = known_names[best_match_index]
                    confidence = max(0, 100 - (best_distance * 10))
            
            detections.append({
                'name': name,
                'confidence': round(confidence, 2),
                'box': [int(x), int(y), int(w), int(h)]
            })
        
        return jsonify({
            'success': True,
            'face_count': len(detections),
            'detections': detections
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get-people')
def get_people():
    """Get list of people in training data"""
    try:
        people = []
        for person_name in os.listdir(KNOWN_FACES_FOLDER):
            person_folder = os.path.join(KNOWN_FACES_FOLDER, person_name)
            if os.path.isdir(person_folder):
                face_count = len([f for f in os.listdir(person_folder) if f.endswith(('.jpg', '.png', '.jpeg'))])
                people.append({
                    'name': person_name,
                    'face_count': face_count
                })
        
        return jsonify({
            'people': people,
            'total': len(people)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete-person/<person_name>', methods=['DELETE'])
def delete_person(person_name):
    """Delete a person from training data"""
    try:
        person_folder = os.path.join(KNOWN_FACES_FOLDER, person_name)
        if os.path.exists(person_folder):
            import shutil
            shutil.rmtree(person_folder)
            
            # Retrain
            thread = threading.Thread(target=train_faces)
            thread.start()
            
            return jsonify({'message': 'Person deleted and system retraining'})
        
        return jsonify({'error': 'Person not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # Train on startup
    train_faces()
    app.run(debug=True, host='0.0.0.0', port=8000)
