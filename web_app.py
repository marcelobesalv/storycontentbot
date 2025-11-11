from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from markupsafe import escape
from flask_socketio import SocketIO, emit
import threading
import os
import json
import time
from main import MainApp
import logging
from pyngrok import ngrok
import argparse
from functools import wraps
import hashlib
import re
from werkzeug.utils import secure_filename

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
socketio = SocketIO(app, cors_allowed_origins="*")

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'no-sniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline';"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# Authentication settings - Load from config or use defaults
def load_auth_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        auth_config = config.get('web_auth', {})
        return {
            'enabled': auth_config.get('enabled', True),
            'username': auth_config.get('username', 'admin'),
            'password_hash': auth_config.get('password_hash', hash_password('admin123'))
        }
    except:
        return {
            'enabled': True,
            'username': 'admin',
            'password_hash': hash_password('admin123')
        }

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Verify password against hash"""
    return hash_password(password) == password_hash

# Load auth configuration
AUTH_CONFIG = load_auth_config()

# Security functions
def sanitize_topic(topic):
    """Sanitize topic input to prevent injection attacks"""
    if not topic:
        return ""
    
    # Remove any potentially dangerous characters
    topic = re.sub(r'[<>"\';\\|`$(){}[\]]', '', str(topic))
    # Limit length
    topic = topic[:100]
    # Remove excessive whitespace
    topic = ' '.join(topic.split())
    return topic

def validate_filename(filename):
    """Validate filename to prevent path traversal attacks"""
    if not filename:
        return False
    
    # Use werkzeug's secure_filename
    secure_name = secure_filename(filename)
    
    # Additional checks
    if (secure_name != filename or 
        '..' in filename or 
        '/' in filename or 
        '\\' in filename or
        not filename.endswith('.mp4')):
        return False
    
    return True

def validate_content_type(content_type):
    """Validate content type input"""
    allowed_types = ['story', 'facts', 'reddit']
    return content_type in allowed_types

def rate_limit_check(session_key='last_request'):
    """Simple rate limiting - max 1 request per 30 seconds"""
    current_time = time.time()
    last_request = session.get(session_key, 0)
    
    if current_time - last_request < 30:
        return False
    
    session[session_key] = current_time
    return True

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AUTH_CONFIG['enabled']:
            return f(*args, **kwargs)
        
        if 'logged_in' not in session or not session['logged_in']:
            if request.endpoint and request.endpoint.startswith('api/'):
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Global variables to track status
current_status = "idle"
current_progress = ""
video_queue = []

class WebSocketLogger:
    """Custom logger that sends messages to web clients via SocketIO"""
    def __init__(self):
        self.messages = []
    
    def log(self, message):
        self.messages.append(message)
        socketio.emit('log_message', {'message': message})
        print(message)  # Also print to console

# Create global logger instance
web_logger = WebSocketLogger()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    if not AUTH_CONFIG['enabled']:
        session['logged_in'] = True
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Rate limiting for login attempts
        if not rate_limit_check('last_login_attempt'):
            flash('Too many login attempts. Please wait 30 seconds.', 'error')
            return render_template('login.html')
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Validate input
        if not username or not password:
            flash('Username and password are required!', 'error')
            return render_template('login.html')
        
        # Sanitize username
        username = re.sub(r'[<>"\';\\|`$(){}[\]]', '', username)[:50]
        
        if (username == AUTH_CONFIG['username'] and 
            verify_password(password, AUTH_CONFIG['password_hash'])):
            
            # Clear and regenerate session to prevent session fixation
            session.clear()
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = time.time()
            session.permanent = True
            
            logger.info(f"Successful login: {username}")
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            logger.warning(f"Failed login attempt: {username}")
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/status')
@login_required
def get_status():
    """Get current bot status"""
    return jsonify({
        'status': current_status,
        'progress': current_progress,
        'video_count': len(os.listdir('output')) if os.path.exists('output') else 0
    })

@app.route('/api/create_video', methods=['POST'])
@login_required
def create_video():
    """Create a new video with specified parameters"""
    global current_status, current_progress
    
    # Rate limiting
    if not rate_limit_check():
        return jsonify({'error': 'Rate limited. Please wait 30 seconds between requests.'}), 429
    
    if current_status != "idle":
        return jsonify({'error': 'Bot is already running'}), 400
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Sanitize and validate inputs
        topic = sanitize_topic(data.get('topic', ''))
        content_type = data.get('content_type', 'story')
        
        if not validate_content_type(content_type):
            return jsonify({'error': 'Invalid content type'}), 400
        
        # Log the request for monitoring
        logger.info(f"Video creation requested by {session.get('username', 'unknown')} - Topic: {topic}, Type: {content_type}")
        
        # Start video creation in background thread
        thread = threading.Thread(target=run_video_creation, args=(topic, content_type))
        thread.daemon = True
        thread.start()
        
        return jsonify({'message': 'Video creation started', 'topic': topic, 'type': content_type})
        
    except Exception as e:
        logger.error(f"Error in create_video: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/config')
@login_required
def get_config():
    """Get current configuration"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Remove sensitive information
        safe_config = config.copy()
        if 'gemini' in safe_config:
            safe_config['gemini']['api_key'] = '***HIDDEN***'
        if 'instagram' in safe_config:
            safe_config['instagram']['password'] = '***HIDDEN***'
        if 'web_auth' in safe_config:
            safe_config['web_auth']['password_hash'] = '***HIDDEN***'
        
        return jsonify(safe_config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_video_creation(topic, content_type):
    """Run video creation in background thread"""
    global current_status, current_progress
    
    try:
        current_status = "running"
        current_progress = "Initializing..."
        
        web_logger.log("🚀 Starting content creation...")
        socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
        
        # Create custom MainApp with web logging
        app_instance = WebMainApp()
        app_instance.set_logger(web_logger)
        
        # Run the creation process
        app_instance.run_with_params(topic, content_type)
        
        current_status = "completed"
        current_progress = "Video creation completed!"
        web_logger.log("✅ Video creation completed successfully!")
        
    except Exception as e:
        current_status = "error"
        current_progress = f"Error: {str(e)}"
        web_logger.log(f"❌ Error during video creation: {str(e)}")
    
    finally:
        socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
        # Reset status after 30 seconds
        threading.Timer(30.0, lambda: reset_status()).start()

def reset_status():
    """Reset status to idle"""
    global current_status, current_progress
    current_status = "idle"
    current_progress = ""
    socketio.emit('status_update', {'status': current_status, 'progress': current_progress})

class WebMainApp(MainApp):
    """Extended MainApp with web logging capabilities"""
    def __init__(self):
        super().__init__()
        self.logger = None
    
    def set_logger(self, logger):
        self.logger = logger
    
    def log(self, message):
        if self.logger:
            self.logger.log(message)
        else:
            print(message)
    
    def run_with_params(self, topic, content_type):
        """Run with specific parameters from web interface"""
        global current_progress
        
        try:
            current_progress = "Generating content..."
            socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
            
            # 1. Generate Content
            if content_type == "reddit":
                from main import RedditScraper
                reddit_scraper = RedditScraper()
                content = reddit_scraper.get_reddit_story(topic)
                self.log(f"📌 Source: {content.get('source', 'Reddit')}")
            elif content_type == "facts":
                content = self.content_generator.generate_content(topic, "facts")
            else:
                content = self.content_generator.generate_content(topic, "story")
            
            if not content:
                raise Exception("Failed to generate content")
            
            self.log(f"📄 Title: {content['title']}")
            self.log(f"📝 Story: {content['story'][:70]}...")
            
            current_progress = "Creating voiceover..."
            socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
            
            # 2. Create Voiceover
            audio_path = self.video_processor.create_voiceover(content['story'])
            if not audio_path:
                raise Exception("Failed to create voiceover")
            
            current_progress = "Processing video..."
            socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
            
            # 3. Get Background Video
            bg_path = self._get_random_background_video()
            if not bg_path:
                raise Exception("No background videos found")
            
            # 4. Create Final Video
            final_video_path = self.video_processor.create_video_ffmpeg(content, audio_path, bg_path)
            
            # Clean up intermediate audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            if not final_video_path:
                raise Exception("Failed to create final video")
            
            current_progress = "Uploading..."
            socketio.emit('status_update', {'status': current_status, 'progress': current_progress})
            
            # 5. Upload to Instagram (if enabled)
            instagram_config = self.config.get("instagram", {})
            if instagram_config.get("auto_upload", False):
                self.uploader.upload(final_video_path, content)
            
            # 6. Upload to YouTube (if enabled)
            youtube_config = self.config.get("youtube", {})
            if youtube_config.get("auto_upload", False):
                self.youtube_uploader.upload_short(final_video_path, content)
            
            self.log(f"🎉 Video created successfully: {os.path.basename(final_video_path)}")
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
            raise e

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('status_update', {'status': current_status, 'progress': current_progress})

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Content Creator Web Interface')
    parser.add_argument('--public', action='store_true', help='Make accessible from internet using ngrok')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on (default: 5000)')
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    print("🌐 Starting Content Creator Web Interface...")
    
    if args.public:
        # Set up ngrok for public access
        try:
            # Kill any existing ngrok processes
            ngrok.kill()
            
            # Create ngrok tunnel
            public_tunnel = ngrok.connect(args.port, "http")
            public_url = public_tunnel.public_url
            
            print("=" * 60)
            print("🚀 PUBLIC ACCESS ENABLED!")
            print("=" * 60)
            print(f"🌍 Public URL: {public_url}")
            print(f"🏠 Local URL: http://localhost:{args.port}")
            print("📱 You can now access this from ANY device with internet!")
            print("🔒 Connection is secure (HTTPS)")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Failed to create public tunnel: {e}")
            print("💡 Try installing ngrok manually: https://ngrok.com/download")
            print("🔄 Falling back to local network only...")
            args.public = False
    
    if not args.public:
        print(f"📱 Local network access: http://your-computer-ip:{args.port}")
        print(f"🏠 Local access: http://localhost:{args.port}")
        print("💡 Use --public flag for internet access")
    
    try:
        socketio.run(app, host='0.0.0.0', port=args.port, debug=False)
    except KeyboardInterrupt:
        if args.public:
            ngrok.kill()
        print("\n👋 Server stopped.")