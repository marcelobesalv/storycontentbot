# 🎬 Social Media Content Creator# 🎬 Social Media Content Creator# 🎬 Auto Content Creator



Automated video creation system with AI content generation and professional TTS.



## 🚀 Quick StartAutomated video creation system with AI content generation and professional TTS.Simple tool to create social media videos automatically.



```bash

# 1. Activate virtual environment

venv\Scripts\activate.bat        # Windows## 🚀 Quick Start## 🚀 Quick Start

source venv/bin/activate         # Linux/Mac



# 2. Run the system

python main.py### Using Activation Scripts (Recommended)1. **Install dependencies:**

```

```cmd```bash

## 📦 Setup

# Windows Batchpip install -r requirements.txt

```bash

# Create virtual environmentactivate.bat```

python -m venv venv



# Activate virtual environment

venv\Scripts\activate.bat        # Windows# PowerShell  2. **Add your background video:**

source venv/bin/activate         # Linux/Mac

.\activate.ps1- Put any long video (.mp4) in `background_videos/` folder

# Install dependencies

pip install -r requirements.txt```- System will use random 60-second clips



# Run the system

python main.py

```### Manual Setup3. **Run:**



## 🛠️ Features```bash```bash



- ✅ **AI Content Generation**: Google Gemini for engaging stories# 1. Activate virtual environmentpython main.py

- ✅ **High-Quality TTS**: Edge-TTS with neural voices  

- ✅ **Ultra-Fast Processing**: FFmpeg for 5-10x speed improvementvenv\Scripts\activate.bat        # Windows```

- ✅ **Smart Video Format**: Auto-crop to vertical (1080x1920)

- ✅ **Dynamic Subtitles**: Fast-changing, mobile-optimized textsource venv/bin/activate         # Linux/Mac

- ✅ **Multi-Platform Ready**: TikTok, Instagram, YouTube Shorts

- ✅ **Optimized File Size**: 30-60MB perfect for all platforms4. **Enter topic** (or press Enter for random)



## 📁 Project Structure# 2. Run the system



```python main.py## 📁 Project Structure

dinero/

├── venv/                    # Virtual environment``````

├── main.py                  # Main application

├── config.json             # Configurationdinero/

├── requirements.txt         # Dependencies

├── background_videos/       # Background video files## 📦 Virtual Environment├── main.py              # Main script

├── output/                 # Generated videos

└── README.md               # Documentation├── config.json          # API keys

```

This project uses a Python virtual environment for dependency isolation:├── requirements.txt     # Dependencies  

## ⚙️ Configuration

├── background_videos/   # Your background videos

Edit `config.json`:

```json```bash└── output/             # Generated videos

{

  "gemini": {# Already created - just activate:```

    "api_key": "your-gemini-api-key"

  },venv\Scripts\activate.bat        # Windows

  "instagram": {

    "username": "your-username", venv\Scripts\Activate.ps1        # PowerShell## ⚙️ Features

    "password": "your-password",

    "auto_upload": falsesource venv/bin/activate         # Linux/Mac- ✅ AI content generation (Google Gemini)

  }

}- ✅ English voiceover (Google TTS)

```

# To deactivate:- ✅ Vertical video format (1080x1920)

## 🎯 Platform Compatibility

deactivate- ✅ Automatic subtitles

| Platform | File Size Limit | Our Output | Status |

|----------|----------------|------------|---------|```- ✅ Instagram Reels upload

| **TikTok** | 72MB (Android) | ~50MB | ✅ Perfect |

| **Instagram Reels** | 4GB | ~50MB | ✅ Perfect |- ✅ Manual upload ready (YouTube Shorts, TikTok)

| **YouTube Shorts** | 256GB | ~50MB | ✅ Perfect |

## 🛠️ Features

## 🔧 Dependencies

## 🎯 Usage

- **google-generativeai**: AI content generation

- **edge-tts**: High-quality text-to-speech- ✅ **AI Content Generation**: Google Gemini for engaging stories1. System generates content about your topic

- **ffmpeg-python**: Video processing

- **moviepy**: Video editing (fallback)- ✅ **High-Quality TTS**: Edge-TTS with neural voices  2. Creates voiceover in English

- **instagrapi**: Instagram API

- **opencv-python**: Computer vision- ✅ **Ultra-Fast Processing**: FFmpeg for 5-10x speed improvement3. Picks random video clip from your background videos



## 📝 Credits- ✅ **Smart Video Format**: Auto-crop to vertical (1080x1920)4. Adds subtitles and combines everything



- **AI**: Google Gemini- ✅ **Dynamic Subtitles**: Fast-changing, mobile-optimized text5. Uploads to Instagram automatically

- **Voice**: Edge-TTS Neural Voices

- **Video**: FFmpeg + MoviePy- ✅ **Multi-Platform Ready**: TikTok, Instagram, YouTube Shorts6. Opens folder for manual upload to YouTube/TikTok



**Ready to create viral content!** 🚀- ✅ **Optimized File Size**: 30-60MB perfect for all platforms

**Ready to create viral content!** 🚀
## 📁 Project Structure

```
dinero/
├── venv/                    # Virtual environment (isolated dependencies)
├── main.py                  # Main application
├── config.json             # Configuration (API keys, settings)
├── requirements.txt         # All dependencies with versions
├── activate.bat            # Windows activation script
├── activate.ps1            # PowerShell activation script
├── background_videos/       # Your background video files
├── output/                 # Generated videos and assets
└── README.md               # This documentation
```

## ⚙️ Configuration

Edit `config.json`:
```json
{
  "gemini": {
    "api_key": "your-gemini-api-key"
  },
  "instagram": {
    "username": "your-username", 
    "password": "your-password",
    "auto_upload": false
  }
}
```

## 🎯 Platform Compatibility

| Platform | File Size Limit | Our Output | Status |
|----------|----------------|------------|---------|
| **TikTok** | 72MB (Android) | ~50MB | ✅ Perfect |
| **Instagram Reels** | 4GB | ~50MB | ✅ Perfect |
| **YouTube Shorts** | 256GB | ~50MB | ✅ Perfect |

## 🔧 Troubleshooting

- **Instagram API errors**: Set `"auto_upload": false` in config
- **Virtual environment issues**: Use provided activation scripts
- **FFmpeg not found**: Auto-detected or install via `winget install Gyan.FFmpeg`

## 📝 Credits

- **AI**: Google Gemini
- **Voice**: Edge-TTS Neural Voices
- **Video**: FFmpeg + MoviePy

**Ready to create viral content!** 🚀