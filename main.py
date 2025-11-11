import os
import time
import json
import random
import subprocess
import re
import requests
from typing import Dict, List

# --- DEPENDENCIES ---
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, CompositeVideoClip, ImageClip
    )
except ImportError:
    VideoFileClip = AudioFileClip = CompositeVideoClip = ImageClip = None

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    Image = ImageDraw = ImageFont = ImageFilter = None

try:
    import edge_tts
    import asyncio
    EDGE_TTS_AVAILABLE = True
    print("✅ Edge TTS available")
except ImportError:
    edge_tts = asyncio = None
    EDGE_TTS_AVAILABLE = False
    print("❌ Edge TTS not available. Please install: pip install edge-tts")

try:
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs
    ELEVENLABS_AVAILABLE = True
    print("✅ ElevenLabs available")
except ImportError:
    ElevenLabs = VoiceSettings = None
    ELEVENLABS_AVAILABLE = False
    print("❌ ElevenLabs not available. Please install: pip install elevenlabs")

try:
    import ffmpeg
    FFMPEG_PYTHON_AVAILABLE = True
    
    # Configure FFmpeg executable paths - use local files first
    import os
    script_dir = os.path.dirname(__file__)
    local_ffmpeg = os.path.abspath(os.path.join(script_dir, 'ffmpeg.exe'))
    local_ffprobe = os.path.abspath(os.path.join(script_dir, 'ffprobe.exe'))
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        # Monkey patch the probe function to use local ffprobe
        original_probe = ffmpeg.probe
        def patched_probe(filename, **kwargs):
            kwargs.setdefault('cmd', local_ffprobe)
            return original_probe(filename, **kwargs)
        ffmpeg.probe = patched_probe
        
        # Monkey patch the run functions to use local ffmpeg
        original_run = ffmpeg.run
        def patched_run(stream_spec, cmd=None, **kwargs):
            if cmd is None:
                cmd = local_ffmpeg
            return original_run(stream_spec, cmd=cmd, **kwargs)
        ffmpeg.run = patched_run
        
        print(f"✅ FFmpeg configured (local): {local_ffmpeg}")
        print(f"✅ FFprobe configured (local): {local_ffprobe}")
    else:
        # Fallback to system installation
        system_ffmpeg = os.path.join(os.environ['LOCALAPPDATA'], 
                                    'Microsoft', 'WinGet', 'Packages', 
                                    'Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe',
                                    'ffmpeg-8.0-essentials_build', 'bin', 'ffmpeg.exe')
        
        if os.path.exists(system_ffmpeg):
            ffmpeg._probe.exe = system_ffmpeg
            ffmpeg._run.exe = system_ffmpeg
            print(f"✅ FFmpeg configured (system): {system_ffmpeg}")
        else:
            print("⚠️ FFmpeg not found, trying system PATH...")
        
except ImportError:
    ffmpeg = None
    FFMPEG_PYTHON_AVAILABLE = False
    edge_tts = None
    asyncio = None

try:
    from instagrapi import Client
except ImportError:
    Client = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

# --- CLASSES ---

class RedditScraper:
    """Scrapes interesting stories from Reddit."""
    
    def __init__(self, used_posts_tracker=None):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.subreddits = [
            # 'todayilearned', 'tifu', 'nosleep', 'LetsNotMeet',
            # 'UnresolvedMysteries', 'TrueScaryStories', 'Glitch_in_the_Matrix',
            # 'shortscarystories', 'WritingPrompts', 'confession', 'relationship_advice',
            # 'AmItheAsshole', 'petpeeves', 'mildlyinteresting', 'showerthoughts',
            # 'unpopularopinion', 'trueoffmychest', 'maliciouscompliance', 'prorevenge',
            # 'nuclearrevenge', 'choosingbeggars', 'entitledparents', 'idontworkherelady',
            # 'talesfromtechsupport', 'talesfromretail', 'talesfromcallcenters',
            # 'paranormal', 'creepyencounters', 'thetruthishere', 'humanoidencounters',
            # 'blackmagicfuckery', 'oddlyterrifying', 'cursedcomments', 'holup',
            # 'crappydesign', 'mildlyinfuriating', 'therewasanattempt', 'facepalm',
            # 'whatcouldgowrong', 'winstupidprizes', 'instantkarma', 'justiceserved',
            # 'madlads', 'nextfuckinglevel', 'damnthatsinteresting', 'interestingasfuck',
            # 'oddlysatisfying', 'mildlysatisfying', 'satisfyingasfuck', 'BeAmazed',
            # 'conspiracy', 'mystery', 'serialkillers', 'unresolvedmysteries',
            # 'rbi', 'whatisthisthing', 'tipofmytongue', 'explainlikeimfive',
            # 'science', 'space', 'futurology', 'technology',
            # 'psychology', 'philosophy', 'history', 'todayilearned',
            # 'coolguides', 'lifeprotips', 'youshouldknow', 'lifehacks'
            'tifu', 'AmItheAsshole'
        ]
        self.used_posts_tracker = used_posts_tracker or []
    
    def _format_time_ago(self, created_utc: float) -> str:
        """Convert Unix timestamp to 'X hours ago' format."""
        if not created_utc:
            return "recently"
        
        current_time = time.time()
        time_diff = current_time - created_utc
        
        hours = int(time_diff / 3600)
        
        if hours < 1:
            minutes = int(time_diff / 60)
            return f"{minutes}m ago" if minutes > 0 else "just now"
        elif hours < 24:
            return f"{hours}h ago"
        else:
            days = int(hours / 24)
            return f"{days}d ago"
    
    def get_reddit_story(self, topic: str = None, avoid_repeats: bool = False, min_score: int = 1000) -> Dict:
        """Scrapes a story from Reddit. Retries with lower thresholds if needed."""
        try:
            # Choose subreddit based on topic or random
            if topic and any(word in topic.lower() for word in ['scary', 'horror', 'ghost', 'creepy', 'paranormal']):
                subreddit = random.choice(['nosleep', 'TrueScaryStories', 'LetsNotMeet', 'paranormal', 'creepyencounters', 'thetruthishere'])
            elif topic and any(word in topic.lower() for word in ['relationship', 'love', 'dating']):
                subreddit = random.choice(['relationship_advice', 'trueoffmychest'])
            elif topic and any(word in topic.lower() for word in ['confession', 'secret', 'admit']):
                subreddit = random.choice(['confession', 'trueoffmychest'])
            elif topic and any(word in topic.lower() for word in ['revenge', 'justice', 'karma']):
                subreddit = random.choice(['prorevenge', 'maliciouscompliance', 'nuclearrevenge', 'instantkarma'])
            elif topic and any(word in topic.lower() for word in ['work', 'job', 'retail', 'customer']):
                subreddit = random.choice(['talesfromretail', 'talesfromtechsupport', 'idontworkherelady', 'choosingbeggars'])
            elif topic and any(word in topic.lower() for word in ['interesting', 'cool', 'amazing', 'facts']):
                subreddit = random.choice(['todayilearned', 'damnthatsinteresting', 'interestingasfuck', 'BeAmazed'])
            elif topic and any(word in topic.lower() for word in ['science', 'space', 'technology', 'future']):
                subreddit = random.choice(['science', 'space', 'futurology', 'technology', 'askscience'])
            else:
                subreddit = random.choice(self.subreddits)
            
            print(f"🔍 Fetching from r/{subreddit}...")
            print(f"   Minimum score threshold: {min_score}")
            
            # Get Reddit JSON data - use top posts from this week for more engaging content
            url = f'https://www.reddit.com/r/{subreddit}/top.json?t=week&limit=100'
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Reddit API returned {response.status_code}")
            
            data = response.json()
            posts = data['data']['children']
            
            # Filter and score posts for engagement (hooky content)
            scored_posts = []
            for post in posts:
                post_data = post['data']
                title = post_data.get('title', '')
                selftext = post_data.get('selftext', '')
                score = post_data.get('score', 0)
                num_comments = post_data.get('num_comments', 0)
                post_id = post_data.get('id', '')
                upvote_ratio = post_data.get('upvote_ratio', 0)
                
                # Skip if already used (when avoid_repeats is enabled)
                if avoid_repeats and post_id in self.used_posts_tracker:
                    continue
                
                # Higher minimum score for more engaging content (use dynamic threshold)
                if (len(selftext) > 200 and len(selftext) < 5000 and 
                    score > min_score and  # Dynamic threshold
                    num_comments > 15 and  # More discussion = more engaging
                    upvote_ratio > 0.84 and  # High approval rate
                    not post_data.get('over_18', False) and
                    not post_data.get('stickied', False) and
                    '[removed]' not in selftext and '[deleted]' not in selftext):
                    
                    # Calculate engagement score - 10x MULTIPLIER for viral content
                    engagement_score = (
                        score * 4.0 +  # Upvotes matter (10x from 0.4)
                        num_comments * 3.0 +  # Discussion matters (10x from 0.3)
                        upvote_ratio * 1000 * 2.0 +  # Approval rate (10x from 100*0.2)
                        (1 if any(hook in title.lower() for hook in 
                         ['secret', 'shocking', 'never', 'why', 'how', 'discovered', 
                          'truth', 'hidden', 'revealed', 'crazy', 'insane', 'unbelievable',
                          'what happened', 'found out', 'ruined', 'saved', 'destroyed']) else 0) * 500  # Hooky title words (10x from 50)
                    )
                    
                    scored_posts.append({
                        'data': post_data,
                        'engagement_score': engagement_score
                    })
            
            if not scored_posts:
                # Retry with progressively lower thresholds until we find something
                if min_score > 500:
                    print(f"⚠️ No posts found with current threshold. Lowering requirements...")
                    return self.get_reddit_story(topic, avoid_repeats=avoid_repeats, min_score=max(500, min_score // 2))
                elif avoid_repeats and self.used_posts_tracker:
                    print("🔄 All engaging posts used! Trying without repeat avoidance...")
                    return self.get_reddit_story(topic, avoid_repeats=False, min_score=1000)
                else:
                    raise Exception("No suitable posts found even with lower thresholds")
            
            # Sort by engagement score and pick from top 20% (weighted random)
            scored_posts.sort(key=lambda x: x['engagement_score'], reverse=True)
            top_posts = scored_posts[:max(1, len(scored_posts) // 5)]  # Top 20%
            
            # Pick from top posts with preference for highest scores
            selected = random.choice(top_posts)
            selected_post = selected['data']
            print(f"📊 Selected post engagement score: {selected['engagement_score']:.0f}")
            post_id = selected_post.get('id', '')
            
            # Clean and format the story
            title = self._clean_reddit_title(selected_post['title'])
            story = self._clean_reddit_text(selected_post['selftext'])
            
            # Truncate story to fit TTS limits (250-400 words for longer content)
            story_words = story.split()
            if len(story_words) > 400:
                story = ' '.join(story_words[:400]) + "..."
            
            # Generate hashtags based on subreddit and content
            hashtags = self._generate_reddit_hashtags(selected_post['subreddit'], title, story)
            
            return {
                'title': title,  # Use full Reddit title (no truncation)
                'story': story,
                'hashtags': hashtags,
                'source': f"r/{selected_post['subreddit']}",
                'reddit_info': {
                    'subreddit': selected_post['subreddit'],
                    'author': selected_post.get('author', 'unknown'),
                    'upvotes': selected_post.get('score', 0),
                    'original_title': selected_post['title'],
                    'post_id': post_id,  # Add post ID for tracking
                    'comments': selected_post.get('num_comments', 0),
                    'time_ago': self._format_time_ago(selected_post.get('created_utc', 0))
                }
            }
            
        except Exception as e:
            print(f"❌ Reddit scraping failed: {e}")
            raise Exception("Reddit scraping failed. Please try again.")
    
    def _clean_reddit_title(self, title: str) -> str:
        """Cleans Reddit title for video use."""
        # Expand common Reddit abbreviations
        title = re.sub(r'\bAITA\b', 'Am I The Asshole', title, flags=re.IGNORECASE)
        title = re.sub(r'\bTIFU\b', 'Today I F***ed Up', title, flags=re.IGNORECASE)
        
        # Remove other common Reddit prefixes
        title = re.sub(r'^(TIL|ELI5|LPT)[\s:]+', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\[.*?\]', '', title)  # Remove [brackets]
        title = title.strip()
        
        # Make it more clickable if too boring
        if not any(word in title.lower() for word in ['secret', 'crazy', 'shocking', 'believe', 'real']):
            title = f"{title}"
        
        return title
    
    def _clean_reddit_text(self, text: str) -> str:
        """Cleans Reddit post text."""
        # Remove Reddit formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
        text = re.sub(r'~~(.*?)~~', r'\1', text)      # Strikethrough
        text = re.sub(r'\^(.*?)\^', r'\1', text)      # Superscript
        text = re.sub(r'&gt;', '', text)             # Quote marks
        text = re.sub(r'\n+', ' ', text)             # Multiple newlines
        text = re.sub(r'\s+', ' ', text)             # Multiple spaces
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove Reddit usernames and subreddit mentions
        text = re.sub(r'/?u/[A-Za-z0-9_-]+', '', text)
        text = re.sub(r'/?r/[A-Za-z0-9_-]+', '', text)
        
        return text.strip()
    
    def _generate_reddit_hashtags(self, subreddit: str, title: str, story: str) -> str:
        """Generates hashtags based on Reddit content."""
        hashtag_map = {
            'nosleep': '#horror #scary #stories',
            'tifu': '#fail #funny #storytime',
            'askreddit': '#askreddit #stories #real',
            'todayilearned': '#facts #mindblown #education',
            'letsnotmeet': '#creepy #truecrime #scary',
            'glitch_in_the_matrix': '#glitch #paranormal #mystery'
        }
        
        return hashtag_map.get(subreddit.lower(), '#reddit #stories #real')
    
    def get_ask_post_with_comments(self, subreddit_list: list = None, avoid_repeats: bool = False, min_comments: int = 100, min_score: int = 1000) -> Dict:
        """Fetches a post from ask-type subreddits with top comments. Retries with lower thresholds if needed."""
        try:
            # Use provided list or default ask subreddits
            if not subreddit_list:
                subreddit_list = ['AskReddit', 'AskMen', 'AskWomen', 'TooAfraidToAsk', 'NoStupidQuestions','AskReddit','AskReddit','AskReddit','AskReddit','AskReddit']
            
            subreddit = random.choice(subreddit_list)
            print(f"🔍 Fetching from r/{subreddit}...")
            print(f"   Minimum thresholds: {min_comments} comments, {min_score} score")
            
            # Get top posts from this week for more engaging questions
            url = f'https://www.reddit.com/r/{subreddit}/top.json?t=week&limit=100'
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Reddit API returned {response.status_code}")
            
            data = response.json()
            posts = data['data']['children']
            
            # Filter and score ask posts for engagement
            scored_posts = []
            for post in posts:
                post_data = post['data']
                title = post_data.get('title', '')
                num_comments = post_data.get('num_comments', 0)
                score = post_data.get('score', 0)
                post_id = post_data.get('id', '')
                upvote_ratio = post_data.get('upvote_ratio', 0)
                
                # Skip if already used (when avoid_repeats is enabled)
                if avoid_repeats and post_id in self.used_posts_tracker:
                    continue
                
                # Higher thresholds for more engaging questions (use dynamic thresholds)
                if (num_comments > min_comments and
                    score > min_score and
                    upvote_ratio > 0.84 and  # High approval
                    not post_data.get('over_18', False) and
                    not post_data.get('stickied', False)):
                    
                    # Calculate question engagement score - 10x MULTIPLIER for viral content
                    engagement_score = (
                        score * 3.0 +  # Upvotes (10x from 0.3)
                        num_comments * 5.0 +  # Comments are more important (10x from 0.5)
                        upvote_ratio * 1000 * 1.0 +  # Approval (10x from 100*0.1)
                        (1 if any(hook in title.lower() for hook in 
                         ['what', 'why', 'how', 'best', 'worst', 'weirdest', 'craziest',
                          'secret', 'ever', 'never', 'most', 'scariest', 'strangest',
                          'regret', 'wish', 'would you', 'have you']) else 0) * 1000  # Question hooks (10x from 100)
                    )
                    
                    scored_posts.append({
                        'data': post_data,
                        'engagement_score': engagement_score
                    })
            
            if not scored_posts:
                # Retry with progressively lower thresholds until we find something
                if min_comments > 50:
                    print(f"⚠️ No posts found with current thresholds. Lowering requirements...")
                    return self.get_ask_post_with_comments(
                        subreddit_list, 
                        avoid_repeats=avoid_repeats,
                        min_comments=max(50, min_comments // 2),
                        min_score=max(500, min_score // 2)
                    )
                elif avoid_repeats and self.used_posts_tracker:
                    print("🔄 All engaging ask posts used! Trying without repeat avoidance...")
                    return self.get_ask_post_with_comments(subreddit_list, avoid_repeats=False, min_comments=100, min_score=1000)
                else:
                    raise Exception("No suitable ask posts found even with lower thresholds")
            
            # Sort by engagement and pick from top posts
            scored_posts.sort(key=lambda x: x['engagement_score'], reverse=True)
            top_posts = scored_posts[:max(1, len(scored_posts) // 5)]  # Top 20%
            
            selected = random.choice(top_posts)
            selected_post = selected['data']
            print(f"📊 Selected ask post engagement score: {selected['engagement_score']:.0f}")
            post_id = selected_post.get('id', '')
            permalink = selected_post.get('permalink', '')
            
            # Fetch comments for this post
            print(f"💬 Fetching comments for post: {selected_post['title'][:50]}...")
            comments_url = f'https://www.reddit.com{permalink}.json?limit=100'
            comments_response = requests.get(comments_url, headers=self.headers, timeout=10)
            
            if comments_response.status_code != 200:
                raise Exception(f"Comments API returned {comments_response.status_code}")
            
            comments_data = comments_response.json()
            
            # Extract top comments (sorted by score)
            top_comments = []
            if len(comments_data) > 1:
                comments_listing = comments_data[1]['data']['children']
                for comment in comments_listing:
                    if comment['kind'] == 't1':  # t1 = comment
                        comment_data = comment['data']
                        body = comment_data.get('body', '')
                        score = comment_data.get('score', 0)
                        
                        # Filter good comments
                        if (len(body) > 20 and len(body) < 2000 and 
                            score > 50 and
                            '[removed]' not in body and '[deleted]' not in body):
                            top_comments.append({
                                'text': self._clean_reddit_text(body),
                                'score': score,
                                'author': comment_data.get('author', 'unknown')
                            })
            
            # Sort by score and take top 3-5 comments
            top_comments.sort(key=lambda x: x['score'], reverse=True)
            top_comments = top_comments[:5]
            
            if not top_comments:
                raise Exception("No good comments found for this post")
            
            # Build the story: Question + Top Comments
            title = self._clean_reddit_title(selected_post['title'])
            
            # Format story with question and top answers (enumerated)
            story_parts = []
            for i, comment in enumerate(top_comments, 1):
                # Truncate long comments
                comment_text = comment['text']
                words = comment_text.split()
                if len(words) > 80:
                    comment_text = ' '.join(words[:80]) + "..."
                # Add enumeration: "1. comment text"
                story_parts.append(f"{i}. {comment_text}")
            
            story = ' '.join(story_parts)
            
            # Ensure story isn't too long for TTS
            story_words = story.split()
            if len(story_words) > 400:
                story = ' '.join(story_words[:400]) + "..."
            
            # Generate hashtags
            hashtags = self._generate_reddit_hashtags(selected_post['subreddit'], title, story)
            
            return {
                'title': title,
                'story': story,
                'hashtags': hashtags,
                'source': f"r/{selected_post['subreddit']}",
                'reddit_info': {
                    'subreddit': selected_post['subreddit'],
                    'author': selected_post.get('author', 'unknown'),
                    'upvotes': selected_post.get('score', 0),
                    'original_title': selected_post['title'],
                    'post_id': post_id,
                    'comments': selected_post.get('num_comments', 0),
                    'time_ago': self._format_time_ago(selected_post.get('created_utc', 0))
                }
            }
            
        except Exception as e:
            print(f"❌ Ask Reddit scraping failed: {e}")
            raise Exception("Ask Reddit scraping failed. Please try again.")
    
    def get_ai_recommended_reddit_post(self, content_type: str = "story", max_retries: int = 5) -> Dict:
        """Uses Reddit API to find top viral posts, then asks Gemini AI to pick the best one based on scroll-stopping potential."""
        
        try:
            print("🔍 Searching Reddit API for viral posts...")
            
            # Choose subreddits based on content type
            if content_type == "ask":
                subreddits = ['AskReddit', 'AskMen', 'AskWomen', 'NoStupidQuestions', 'TooAfraidToAsk']
            else:
                subreddits = ['tifu', 'AmItheAsshole', 'confession', 'trueoffmychest', 'relationship_advice','nuclearrevenge','prorevenge','maliciouscompliance','Confession']
            
            # Fetch top posts from this week from Reddit API
            all_posts = []
            for subreddit in subreddits:
                try:
                    url = f'https://www.reddit.com/r/{subreddit}/top.json?t=week&limit=50'
                    response = requests.get(url, headers=self.headers, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        posts = data['data']['children']
                        
                        for post in posts:
                            post_data = post['data']
                            score = post_data.get('score', 0)
                            num_comments = post_data.get('num_comments', 0)
                            selftext = post_data.get('selftext', '')
                            post_id = post_data.get('id', '')
                            
                            # Skip if already used
                            if post_id in self.used_posts_tracker:
                                continue
                            
                            # Filter for high-quality posts
                            if content_type == "ask":
                                if score > 1000 and num_comments > 100 and not post_data.get('over_18', False):
                                    all_posts.append({
                                        'title': post_data['title'],
                                        'url': f"https://www.reddit.com{post_data['permalink']}",
                                        'subreddit': post_data['subreddit'],
                                        'score': score,
                                        'comments': num_comments,
                                        'id': post_id
                                    })
                            else:
                                if (score > 1000 and len(selftext) > 200 and 
                                    not post_data.get('over_18', False) and
                                    '[removed]' not in selftext and '[deleted]' not in selftext):
                                    all_posts.append({
                                        'title': post_data['title'],
                                        'url': f"https://www.reddit.com{post_data['permalink']}",
                                        'subreddit': post_data['subreddit'],
                                        'score': score,
                                        'comments': num_comments,
                                        'id': post_id,
                                        'preview': selftext[:200]
                                    })
                    
                except Exception as e:
                    print(f"⚠️ Could not fetch from r/{subreddit}: {e}")
                    continue
            
            if not all_posts:
                raise Exception("No suitable viral posts found on Reddit this week. Try manual selection instead.")
            
            print(f"✅ Found {len(all_posts)} viral posts from Reddit API")
            
            # Now ask Gemini AI to pick the BEST one based on scroll-stopping potential
            if not genai:
                # Fallback: pick highest scored post if no Gemini
                print("⚠️ Gemini not available, picking highest scored post")
                all_posts.sort(key=lambda x: x['score'], reverse=True)
                selected_post = all_posts[0]
            else:
                print("🤖 Asking Gemini AI to select the most scroll-stopping post...")
                
                # Create a list of posts for Gemini to analyze
                posts_summary = "\n\n".join([
                    f"Option {i+1}:\nTitle: {p['title']}\nSubreddit: r/{p['subreddit']}\nUpvotes: {p['score']}\nComments: {p['comments']}\nURL: {p['url']}"
                    for i, p in enumerate(all_posts[:10])  # Limit to top 10 to save tokens
                ])
                
                prompt = f"""You are a viral content expert. Below are {min(10, len(all_posts))} top Reddit posts from this week.

Your task: Pick the ONE post with the most SCROLL-STOPPING, VIRAL potential.

Consider:
1. Does the title create IMMEDIATE curiosity?
2. Is it relatable/shareable?
3. Does it have emotional hook (shock, humor, drama)?
4. Would it stop someone mid-scroll?
5. Is the engagement (upvotes + comments) strong?

Posts:
{posts_summary}

Respond with ONLY the option number (1-{min(10, len(all_posts))}) of the most viral post.
Just the number, nothing else."""

                try:
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    response = model.generate_content(prompt)
                    
                    if response.text:
                        # Extract number from response
                        import re
                        match = re.search(r'\d+', response.text.strip())
                        if match:
                            choice = int(match.group()) - 1
                            if 0 <= choice < len(all_posts[:10]):
                                selected_post = all_posts[choice]
                                print(f"✅ AI selected: Option {choice + 1}")
                            else:
                                selected_post = all_posts[0]
                        else:
                            selected_post = all_posts[0]
                    else:
                        selected_post = all_posts[0]
                except Exception as e:
                    print(f"⚠️ AI selection failed: {e}, using highest scored post")
                    selected_post = all_posts[0]
            
            print(f"🎯 Selected: {selected_post['title'][:60]}...")
            print(f"📊 {selected_post['score']} upvotes, {selected_post['comments']} comments")
            print(f"🔗 {selected_post['url']}")
            
            # Now fetch the full post data
            post_url = f"https://www.reddit.com/r/{selected_post['subreddit']}/comments/{selected_post['id']}.json"
            response = requests.get(post_url, headers=self.headers, timeout=10)
            
            # Now fetch the full post data
            post_url = f"https://www.reddit.com/r/{selected_post['subreddit']}/comments/{selected_post['id']}.json"
            response = requests.get(post_url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch post: HTTP {response.status_code}")
            
            data = response.json()
            
            if not data or len(data) < 1:
                raise Exception("Invalid post data received")
            
            post_data = data[0]['data']['children'][0]['data']
            
            # Check if it's an Ask post (has comments) or regular story
            if content_type == "ask":
                # Get comments
                comments_data = data[1]['data']['children'] if len(data) > 1 else []
                
                top_comments = []
                for comment in comments_data:
                    if comment['kind'] == 't1':
                        comment_data = comment['data']
                        body = comment_data.get('body', '')
                        score = comment_data.get('score', 0)
                        
                        if (len(body) > 20 and len(body) < 2000 and 
                            score > 50 and
                            '[removed]' not in body and '[deleted]' not in body):
                            top_comments.append({
                                'text': self._clean_reddit_text(body),
                                'score': score,
                                'author': comment_data.get('author', 'unknown')
                            })
                
                top_comments.sort(key=lambda x: x['score'], reverse=True)
                top_comments = top_comments[:5]
                
                if not top_comments:
                    raise Exception("No suitable comments found in this post")
                
                # Build story with question and answers
                title = self._clean_reddit_title(post_data['title'])
                story_parts = []
                for i, comment in enumerate(top_comments, 1):
                    comment_text = comment['text']
                    words = comment_text.split()
                    if len(words) > 80:
                        comment_text = ' '.join(words[:80]) + "..."
                    story_parts.append(f"{i}. {comment_text}")
                
                story = ' '.join(story_parts)
            else:
                # Regular story post
                title = self._clean_reddit_title(post_data['title'])
                story = self._clean_reddit_text(post_data.get('selftext', ''))
                
                if len(story) < 200:
                    raise Exception("Story too short")
            
            # Truncate if needed
            story_words = story.split()
            if len(story_words) > 400:
                story = ' '.join(story_words[:400]) + "..."
            
            hashtags = self._generate_reddit_hashtags(post_data['subreddit'], title, story)
            
            print(f"✅ AI-recommended post fetched successfully!")
            
            return {
                'title': title,
                'story': story,
                'hashtags': hashtags,
                'source': f"r/{post_data['subreddit']} (AI recommended)",
                'reddit_info': {
                    'subreddit': post_data['subreddit'],
                    'author': post_data.get('author', 'unknown'),
                    'upvotes': post_data.get('score', 0),
                    'original_title': post_data['title'],
                    'post_id': selected_post['id'],
                    'comments': post_data.get('num_comments', 0),
                    'time_ago': self._format_time_ago(post_data.get('created_utc', 0))
                }
            }
            
        except Exception as e:
            print(f"❌ AI Reddit recommendation failed: {e}")
            raise Exception(f"AI Reddit recommendation failed: {e}")


class ContentGenerator:
    """Handles AI content generation and parsing."""
    def __init__(self, config: Dict):
        self.config = config
        if genai and "gemini" in self.config:
            genai.configure(api_key=self.config["gemini"]["api_key"])
        
        # Viral Hook Matrix - Engineered for scroll-stopping engagement
        self.hook_patterns = {
            "pattern_interrupts": [
                "Stop scrolling.",
                "Wait, what?",
                "This changes everything.",
                "Nobody talks about this.",
                "Delete this later...",
                "I shouldn't be telling you this.",
                "This is actually insane.",
                "POV:",
                "Warning:",
                "Attention:",
            ],
            "psychological_triggers": [
                "You've been lied to about {topic}",
                "The truth about {topic} they don't want you to know",
                "I wish someone told me this about {topic} sooner",
                "This {topic} secret changed my life",
                "Why nobody talks about {topic}",
                "The dark side of {topic}",
                "What they're hiding about {topic}",
                "I tried {topic} for 30 days and...",
                "Before you {action}, watch this",
                "This is why you're failing at {topic}",
            ],
            "curiosity_gaps": [
                "...and what happened next shocked everyone",
                "...but here's what they don't tell you",
                "...and this is the crazy part",
                "...wait until you hear this",
                "...but the last one is mind-blowing",
                "...and number 3 will change everything",
                "...the ending will surprise you",
                "...but there's a catch",
                "...and this is where it gets interesting",
                "...you won't believe what I found",
            ],
            "power_phrases": [
                "Here's why:",
                "Let me explain:",
                "This is huge:",
                "Pay attention:",
                "Real talk:",
                "Controversial take:",
                "Hot take:",
                "Unpopular opinion:",
                "Game changer:",
                "Plot twist:",
            ],
            "viral_structures": [
                "{interrupt} {topic} isn't what you think. {gap}",
                "{trigger} {power} {story}",
                "{power} {topic}. {gap}",
                "{interrupt} I discovered something about {topic}. {gap}",
                "{trigger} And this is what everyone gets wrong. {gap}",
            ],
        }
    
    def _generate_viral_hook(self, topic: str, content_type: str = "story") -> str:
        """Generates a scroll-stopping hook using the viral matrix."""
        import random
        
        # Select random elements from each category
        interrupt = random.choice(self.hook_patterns["pattern_interrupts"])
        trigger = random.choice(self.hook_patterns["psychological_triggers"]).format(topic=topic, action="start")
        gap = random.choice(self.hook_patterns["curiosity_gaps"])
        power = random.choice(self.hook_patterns["power_phrases"])
        
        # Select a viral structure and fill it
        structure = random.choice(self.hook_patterns["viral_structures"])
        
        hook = structure.format(
            interrupt=interrupt,
            topic=topic,
            trigger=trigger,
            gap=gap,
            power=power,
            story=""
        )
        
        # Clean up extra spaces
        hook = " ".join(hook.split())
        
        return hook

    def generate_content(self, topic: str = None, content_type: str = "story") -> Dict:
        """Generates content using Gemini AI with viral hooks."""
        if not topic:
            topics = ["mystery", "adventure", "science", "history", "technology", "nature", "space", "ocean", "animals", "travel", "food", "art", "music", "sports", "gaming", "future", "secrets", "discoveries", "legends", "facts"]
            topic = random.choice(topics)
        
        print(f"🤖 Generating {content_type} content for topic: {topic}...")
        
        # Generate viral hook for inspiration
        viral_hook = self._generate_viral_hook(topic, content_type)
        print(f"🎯 Hook inspiration: {viral_hook[:60]}...")

        if content_type == "facts":
            prompt = f"""
            Create VIRAL content about surprising facts related to "{topic}".
            Your response MUST be a valid JSON object.

            VIRAL HOOK FRAMEWORK - Use these psychological triggers:
            
            PATTERN INTERRUPTS: Start with phrases like "Stop scrolling", "Wait what?", "This is actually insane"
            PSYCHOLOGICAL TRIGGERS: "You've been lied to", "They don't want you to know", "This changed everything"
            CURIOSITY GAPS: "...but here's the crazy part", "...wait until you hear this", "...the last one is mind-blowing"
            POWER PHRASES: "Here's why:", "Real talk:", "Plot twist:", "Game changer:"
            
            Hook Inspiration: "{viral_hook}"

            Requirements:
            - OPEN with a SCROLL-STOPPING hook (use pattern interrupt + curiosity gap)
            - Find SHOCKING, UNBELIEVABLE facts that sound fake but are 100% real
            - Use psychological triggers: scarcity, secrets, forbidden knowledge
            - Create curiosity gaps that force people to keep watching
            - Make it SHAREABLE - people should want to tell others
            - Facts must be VERIFIABLE but completely MIND-BLOWING

            The JSON object should have these exact keys:
            - "title": A VIRAL hook title (max 50 chars) using pattern interrupts or psychological triggers
            - "story": Start with hook, then present 3-4 INSANE facts (150-200 words) with curiosity gaps
            - "hashtags": A single string with exactly 3 relevant hashtags, one worded, each starting with # and in lowercase

            VIRAL Title Formulas:
            - "Stop. {topic} is NOT what you think"
            - "They HIDE this about {topic}"
            - "This {topic} secret is ILLEGAL in 3 countries"
            - "POV: You discover the truth about {topic}"
            - "Delete this. {topic} companies don't want you knowing"

            Example JSON response:
            {{
              "title": "Stop. McDonald's is hiding THIS from you",
              "story": "Wait, what? Only 2 people on Earth know Coca-Cola's recipe... and they're NEVER allowed to travel together. But here's the crazy part - McDonald's is even more secretive. Their ice cream machines 'break' so often that someone created a live tracker. Plot twist: They own more real estate than ANY company on Earth. They're not a restaurant. They're a real estate empire that happens to sell burgers. The golden arches? More recognizable than the Christian cross. And this is where it gets insane - they make MORE money from rent than from food. You've been lied to about what McDonald's actually is.",
              "hashtags": "#mcdonalds #secrets #mindblown"
            }}
            """
        else:
            prompt = f"""
            Create VIRAL storytelling content about "{topic}".
            Your response MUST be a valid JSON object.

            VIRAL HOOK FRAMEWORK - Engineer for maximum engagement:
            
            PATTERN INTERRUPTS: "Stop scrolling", "Nobody talks about this", "This changes everything"
            PSYCHOLOGICAL TRIGGERS: "The truth they hide", "Why you're failing at", "I shouldn't tell you this"
            CURIOSITY GAPS: "...and what happened next", "...but here's the catch", "...you won't believe"
            POWER PHRASES: "Here's why:", "Real talk:", "Let me explain:", "Pay attention:"
            
            Hook Inspiration: "{viral_hook}"

            Requirements:
            - OPEN with a PATTERN INTERRUPT that forces people to stop scrolling
            - Use PSYCHOLOGICAL TRIGGERS: fear of missing out, forbidden knowledge, controversy
            - Build CURIOSITY GAPS that make it impossible to stop watching
            - Include POWER PHRASES that command attention
            - Make it EMOTIONALLY CHARGED - people should FEEL something
            - End with a hook that leaves them wanting more

            The JSON object should have these exact keys:
            - "title": A SCROLL-STOPPING hook (max 50 chars) that demands attention
            - "story": Hook opener + engaging story (150-200 words) with curiosity gaps embedded
            - "hashtags": A single string with exactly 3 viral hashtags, one worded, each starting with # and in lowercase

            VIRAL Title Formulas:
            - "Stop. This {topic} truth will shock you"
            - "POV: You finally learn the truth about {topic}"
            - "Warning: {topic} isn't what they told you"
            - "I tried {topic} for 30 days and THIS happened"
            - "Nobody talks about this {topic} secret"

            Example JSON response:
            {{
              "title": "Stop. The ocean is hiding THIS from you",
              "story": "Wait, what? We've explored less than 5% of our oceans. That means 95% is a COMPLETE mystery. But here's the crazy part - scientists think there are over 1 MILLION species down there we've never seen. Plot twist: In 2019, they found an underwater waterfall TALLER than Angel Falls. The pressure would crush you instantly... yet life THRIVES down there. Real talk: Creatures with no eyes. Fish that make their own light. Organisms surviving in temperatures that would melt metal. And this is where it gets insane - we know more about Mars than our own ocean. What else is hiding in that 95%? What secrets are waiting in the deep?",
              "hashtags": "#ocean #mystery #mindblowing"
            }}
            """
        
        try:
            if not genai:
                raise ImportError("Google Gemini library not available.")
            
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)
            
            if response.text:
                return self._parse_json_response(response.text)
            else:
                print("⚠️ AI response was empty or filtered.")
                raise Exception("AI content generation failed. Please try again.")
        except Exception as e:
            print(f"❌ AI Error: {e}")
            raise Exception("AI content generation failed. Please try again.")

    def _parse_json_response(self, text: str) -> Dict:
        """Parses the JSON response from the AI."""
        try:
            # Clean the response to extract only the JSON part
            json_str = text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parsing Error: {e}. Response was:\n{text}")
            return None



class FFmpegVideoProcessor:
    """Ultra-fast video processor using FFmpeg directly."""
    def __init__(self, config: Dict):
        self.config = config.get("video_settings", {})
        self.output_path = self.config.get("output_path", "output/")
        os.makedirs(self.output_path, exist_ok=True)
        self.last_tts_engine = "Edge-TTS"  # Track which TTS engine was used
        
        # Initialize ElevenLabs client if available
        self.elevenlabs_client = None
        if ELEVENLABS_AVAILABLE and config.get("instagram", {}).get("auto_upload", False):
            elevenlabs_config = config.get("elevenlabs", {})
            api_key = elevenlabs_config.get("api_key")
            if api_key:
                self.elevenlabs_client = ElevenLabs(api_key=api_key)
                print("✅ ElevenLabs client initialized")
            else:
                print("⚠️ ElevenLabs API key not found in config")
    
    def _detect_narrator_gender(self, text: str, title: str = "") -> str:
        """
        Detects the narrator's gender from the story content.
        Returns: 'male', 'female', or 'neutral' (defaults to female)
        """
        combined_text = f"{title} {text}".lower()
        
        # First-person indicators
        male_indicators = [
            r'\bmy wife\b', r'\bmy girlfriend\b', r'\bmy ex-wife\b', r'\bmy ex-girlfriend\b',
            r'\bmy fiancee\b', r'\bmy bride\b', r'\bshe dumped me\b', r'\bshe left me\b',
            r'\bshe cheated on me\b', r'\bi\s+\(?\d*m\)?', r'\bm\d+\b',  # e.g., "I (32M)" or "M32"
            r'\bas a man\b', r'\bas a guy\b', r'\bas a husband\b', r'\bas a father\b', r'\bas a dad\b',
            r'\bmy son\b', r'\bmy daughter\b', r'\bmy kids\b', r'\bmy children\b',
            r'\bfather of\b', r'\bdad of\b'
        ]
        
        female_indicators = [
            r'\bmy husband\b', r'\bmy boyfriend\b', r'\bmy ex-husband\b', r'\bmy ex-boyfriend\b',
            r'\bmy fiance\b', r'\bmy groom\b', r'\bhe dumped me\b', r'\bhe left me\b',
            r'\bhe cheated on me\b', r'\bi\s+\(?\d*f\)?', r'\bf\d+\b',  # e.g., "I (32F)" or "F32"
            r'\bas a woman\b', r'\bas a girl\b', r'\bas a wife\b', r'\bas a mother\b', r'\bas a mom\b',
            r'\bmy son\b', r'\bmy daughter\b', r'\bmy kids\b', r'\bmy children\b',
            r'\bmother of\b', r'\bmom of\b', r'\bpregnant\b', r'\bpregnancy\b'
        ]
        
        # Count matches
        male_score = sum(1 for pattern in male_indicators if re.search(pattern, combined_text))
        female_score = sum(1 for pattern in female_indicators if re.search(pattern, combined_text))
        
        print(f"🔍 Gender detection - Male indicators: {male_score}, Female indicators: {female_score}")
        
        # Determine gender
        if male_score > female_score:
            print("👨 Detected narrator: Male")
            return 'male'
        elif female_score > male_score:
            print("👩 Detected narrator: Female")
            return 'female'
        else:
            # Default to male (neutral voice)
            print("⚪ Neutral/Unclear - Defaulting to male voice")
            return 'male'
        
    def create_voiceover(self, text: str, gender: str = None, tts_engine: str = None) -> str:
        """Creates a voiceover file using ElevenLabs (preferred), or Edge-TTS (fallback)."""
        print("🎤 Creating voiceover...")
        text = self._clean_text_for_tts(text)
        
        # Validate cleaned text
        if not text or len(text.strip()) < 5:
            print("⚠️ Cleaned text is too short, using original.")
            text = self._clean_text_for_tts(text, minimal=True)

        # Auto-detect gender if not provided
        if gender is None:
            gender = 'male'  # default
        
        print(f"🎤 Selected voice gender: {gender.upper()}")

        output_file = os.path.join(self.output_path, f"voice_{int(time.time())}.mp3")
        
        # Try ElevenLabs first if available and no specific engine requested
        if (tts_engine is None or tts_engine == "elevenlabs") and self.elevenlabs_client:
            try:
                print("🎙️ Using ElevenLabs TTS...")
                return self._create_elevenlabs_voiceover(text, gender, output_file)
            except Exception as e:
                print(f"⚠️ ElevenLabs TTS failed: {e}")
                print("🔄 Falling back to Edge TTS...")
        
        # Fallback to Edge TTS
        if not EDGE_TTS_AVAILABLE:
            print("❌ No TTS engine available. Please install: pip install edge-tts")
            raise Exception("No TTS engine available.")

        print(f"🎵 Using Edge TTS (Gender: {gender})...")
        
        # Edge TTS voice options based on gender
        male_voices = [
            "en-US-DavisNeural", "en-US-ChristopherNeural", "en-US-GuyNeural",
            "en-US-JacobNeural", "en-US-JasonNeural", "en-US-TonyNeural",
            "en-GB-RyanNeural", "en-AU-WilliamNeural"
        ]
        
        female_voices = [
            "en-US-AriaNeural", "en-US-JennyNeural", "en-US-MichelleNeural",
            "en-GB-SoniaNeural", "en-AU-NatashaNeural"
        ]
        
        # Select voice list based on gender
        if gender == 'male':
            voice_options = male_voices.copy()
        else:
            voice_options = female_voices.copy()

        random.shuffle(voice_options)
        
        for i, voice in enumerate(voice_options):
            try:
                print(f"🎯 Trying voice {i+1}/{len(voice_options)}: {voice}")
                
                async def generate_speech():
                    communicate = edge_tts.Communicate(text, voice)
                    await communicate.save(output_file)

                asyncio.run(generate_speech())
                
                if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
                    print(f"✅ Voiceover created with Edge TTS: {output_file}")
                    self.last_tts_engine = "Edge-TTS"
                    return output_file
                else:
                    if os.path.exists(output_file):
                        os.remove(output_file)
                    
            except Exception as e:
                print(f"⚠️ Voice {voice} failed: {e}")
                if os.path.exists(output_file):
                    os.remove(output_file)
                continue
        
        # Last resort: simplified text
        print("🔄 All voices failed, trying with simplified text...")
        try:
            simplified_text = text[:500] + "..." if len(text) > 500 else text
            simplified_text = ' '.join(simplified_text.split())
            
            print(f"📝 Simplified text ({len(simplified_text)} chars): {simplified_text[:50]}...")
            
            async def generate_simple_speech():
                communicate = edge_tts.Communicate(simplified_text, "en-US-AriaNeural")
                await communicate.save(output_file)

            asyncio.run(generate_simple_speech())
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 100:
                print(f"✅ Voiceover created with simplified text: {output_file}")
                self.last_tts_engine = "Edge-TTS"
                return output_file
            
        except Exception as e:
            print(f"❌ Simplified text also failed: {e}")
        
        print("❌ All TTS attempts failed.")
        raise Exception("TTS creation failed with all attempts. Please try again.")

    def _create_elevenlabs_voiceover(self, text: str, gender: str, output_file: str) -> str:
        """Creates voiceover using ElevenLabs API."""
        try:
            # ElevenLabs voice IDs based on gender
            # You can find more voices at: https://elevenlabs.io/voice-library
            male_voices = [
                "pNInz6obpgDQGcFmaJgB",  # Adam - Deep and resonant
                "VR6AewLTigWG4xSOukaG",  # Arnold - Strong and authoritative
                "ErXwobaYiN019PkySvjV",  # Antoni - Well-rounded and versatile
                "yoZ06aMxZJJ28mfd3POQ",  # Sam - Dynamic and expressive
            ]
            
            female_voices = [
                "EXAVITQu4vr4xnSDxMaL",  # Bella - Soft and pleasant
                "21m00Tcm4TlvDq8ikWAM",  # Rachel - Clear and articulate
                "AZnzlk1XvdvUeBnXmlld",  # Domi - Energetic and youthful
                "MF3mGyEYCl7XYWbV9V6O",  # Elli - Warm and friendly
            ]
            
            # Select voice based on gender
            voice_id = random.choice(male_voices if gender == 'male' else female_voices)
            
            print(f"🎙️ Using ElevenLabs voice ID: {voice_id}")
            
            # Generate audio with ElevenLabs
            response = self.elevenlabs_client.text_to_speech.convert(
                voice_id=voice_id,
                optimize_streaming_latency="0",
                output_format="mp3_44100_128",
                text=text,
                model_id="eleven_multilingual_v2",  # High quality model
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.75,
                    style=0.0,
                    use_speaker_boost=True
                )
            )
            
            # Save the audio file
            with open(output_file, "wb") as f:
                for chunk in response:
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
                print(f"✅ Voiceover created with ElevenLabs: {output_file}")
                self.last_tts_engine = "ElevenLabs"
                return output_file
            else:
                raise Exception("Generated audio file is too small or doesn't exist")
                
        except Exception as e:
            print(f"❌ ElevenLabs TTS error: {e}")
            if os.path.exists(output_file):
                os.remove(output_file)
            raise

    def _clean_text_for_tts(self, text: str, minimal: bool = False) -> str:
        """Removes unwanted markers from text for cleaner TTS."""
        import re
        print(f"🔍 Cleaning text for TTS: {text[:70]}...")
        
        if minimal:
            # Minimal cleaning - only basic safety
            text = re.sub(r'[^\w\s.,!?;:\'-]', ' ', text)  # Keep only safe characters
            text = re.sub(r'\s+', ' ', text).strip()       # Collapse whitespace
        else:
            # Full cleaning
            original_text = text
            text = re.sub(r'\*[\w\s]+\*', '', text)        # *VOICEOVER*, *NARRATOR*
            # Remove parentheses EXCEPT age/gender markers like (32M), (28F), etc.
            text = re.sub(r'\((?!\d+[MFmf]\))([^)]+)\)', '', text)  # Remove (Visuals: ...), (Scene: ...) but keep (32M)
            text = re.sub(r'\[[^\]]+\]', '', text)         # [stage directions]
            text = re.sub(r'VOICEOVER:|NARRATOR:|SCENE:', '', text, flags=re.IGNORECASE)
            
            # Clean up URLs, special characters that might break TTS
            text = re.sub(r'https?://[^\s]+', '', text)    # Remove URLs
            text = re.sub(r'[^\w\s.,!?;:\'()\-]', '', text)  # Keep only safe characters + parentheses for age markers
            text = re.sub(r'\s+', ' ', text).strip()       # Collapse whitespace
            
            # Ensure we have valid content
            if not text or len(text.strip()) < 10:
                print("⚠️ Cleaned text too short, using minimal cleanup")
                return self._clean_text_for_tts(original_text, minimal=True)
        
        print(f"📝 Cleaned text ({len(text)} chars): {text[:70]}...")
        return text
    
    def _normalize_audio(self, audio_file: str) -> None:
        """
        Normalizes audio to remove reverb/echo artifacts and ensure consistent volume.
        Uses FFmpeg for audio processing.
        """
        try:
            import subprocess
            temp_file = audio_file.replace('.mp3', '_temp.mp3')
            
            # FFmpeg command to normalize audio and remove echo/reverb:
            # - highpass filter to remove low-frequency rumble
            # - loudnorm for consistent volume
            # - compand to reduce dynamic range (helps with reverb)
            cmd = [
                'ffmpeg',
                '-i', audio_file,
                '-af', 'highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,compand=attacks=0.3:decays=0.8:points=-80/-80|-45/-45|-27/-25|0/-7:soft-knee=6:gain=0:volume=0',
                '-ar', '22050',  # Match TTS sample rate
                '-ac', '1',      # Mono
                '-b:a', '128k',  # Good quality
                '-y',
                temp_file
            ]
            
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Replace original with normalized version
            if os.path.exists(temp_file):
                os.replace(temp_file, audio_file)
                
        except Exception as e:
            # If normalization fails, just use original audio
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def _create_reddit_card(self, reddit_info: dict, output_path: str, card_style: str = "black") -> tuple:
        """
        Creates a Reddit-style link post card with improved horizontal spacing,
        capsule-shaped footer buttons, and support for image icons.
        Card height is dynamically calculated based on title length.
        
        Returns:
            tuple: (card_path, reading_time_seconds) - Path to the card and time needed to read the title
        """
        try:

            # --- CONFIGURATION ---
            card_width = 900
            padding = 40
            radius = 12
            scale = 6
            
            # --- TEMPORARY SETUP FOR TEXT MEASUREMENT ---
            # We need to create a temporary draw context to measure text before knowing final height
            temp_img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            temp_draw = ImageDraw.Draw(temp_img)
            
            # Load fonts for measurement
            def load_font(paths, size):
                for path in paths:
                    try:
                        return ImageFont.truetype(path, size * scale)
                    except IOError:
                        try: 
                            return ImageFont.truetype(os.path.basename(path), size * scale)
                        except IOError:
                            continue
                return ImageFont.load_default()

            font_bold_paths = ["arialbd.ttf", "fonts/IBMPlexSans-Bold.ttf"]
            title_font = load_font(font_bold_paths, 32)  # Increased from 24
            
            # Calculate title height
            title = reddit_info.get('original_title', 'Why are there so many "lady-boys" in Thailand?')
            content_width = (card_width - padding * 2) * scale
            
            def wrap_text(text, font, max_width, draw_ctx):
                words, lines = text.split(), []
                current_line = ""
                for word in words:
                    test_line = current_line + word + " "
                    if draw_ctx.textbbox((0, 0), test_line.rstrip(), font=font)[2] <= max_width:
                        current_line = test_line
                    else:
                        lines.append(current_line.strip())
                        current_line = word + " "
                lines.append(current_line.strip())
                return lines

            title_lines = wrap_text(title, title_font, content_width, temp_draw)
            title_line_h = temp_draw.textbbox((0, 0), "Ag", font=title_font)[3] + (15 * scale)  # Increased from 10 to 15
            
            # Calculate dynamic card height with increased spacing for larger fonts
            header_height = 65  # Increased from 50 for larger header fonts
            title_height = len(title_lines) * (title_line_h / scale) + 15  # Increased spacing from 10 to 15
            link_height = 30  # Increased from 25 for larger link font
            footer_height = 75  # Increased from 60 for larger footer buttons
            
            card_height = int(header_height + title_height + link_height + footer_height + padding)
            
            # Ensure minimum height
            card_height = max(card_height, 220)  # Increased from 200
            
            ss_width, ss_height = card_width * scale, card_height * scale
            ss_padding, ss_radius = padding * scale, radius * scale
            
            # --- UI PALETTE ---
            colors = {}
            if card_style == "black":
                colors = {
                    "bg": (10, 10, 10),        
                    "card": (26, 26, 27),       
                    "shadow": (0, 0, 0, 100),   
                    "title": (215, 218, 220),     
                    "link": (109, 158, 235),     
                    "muted": (129, 131, 132),    
                    "accent": (255, 69, 0),      
                    "button_bg": (39, 40, 41),   
                    "button_fg": (215, 218, 220), 
                    "button_active_bg": (255, 69, 0),
                    "button_active_fg": (255, 255, 255),
                    "join_button_bg": (0, 121, 211),
                    "join_button_fg": (0, 0, 0),     
                }
            else: # Light mode
                colors = {
                    "bg": (218, 224, 230), "card": (255, 255, 255), "shadow": (0, 0, 0, 70),
                    "title": (28, 28, 28), "link": (0, 121, 211), "muted": (78, 83, 86),
                    "accent": (255, 69, 0), "button_bg": (237, 239, 241), "button_fg": (28, 28, 28),
                    "button_active_bg": (255, 69, 0), "button_active_fg": (255, 255, 255),
                    "join_button_bg": (0, 121, 211), "join_button_fg": (255, 255, 255),
                }

            # --- IMAGE SETUP ---
            margin = 0  # Removed margin for cleaner look
            base_w, base_h = ss_width, ss_height  # No extra margin
            base = Image.new('RGBA', (base_w, base_h), colors["card"])  # Use card color as base
            
            # Shadow (optional - can be removed if not needed)
            # shadow = Image.new('RGBA', (ss_width, ss_height), (0, 0, 0, 0))
            # ImageDraw.Draw(shadow).rounded_rectangle([(0, 0), (ss_width, ss_height)], radius=ss_radius, fill=colors["shadow"])
            # shadow = shadow.filter(ImageFilter.GaussianBlur(8 * scale))
            # base.paste(shadow, (0, 0), shadow)

            # Card mask for rounded corners
            mask = Image.new('L', (ss_width, ss_height), 0)
            ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (ss_width, ss_height)], radius=ss_radius, fill=255)
            
            # Apply mask to base
            base.putalpha(mask)

            draw = ImageDraw.Draw(base)
            
            # --- FONTS ---
            def load_font(paths, size):
                for path in paths:
                    try:
                        return ImageFont.truetype(path, size * scale)
                    except IOError:
                        # Try to load from a system path if direct path fails
                        try: 
                            return ImageFont.truetype(os.path.basename(path), size * scale)
                        except IOError:
                            continue
                print(f"Warning: Could not load any of {paths}. Using default font.")
                return ImageFont.load_default()

            # Mock font paths for testing
            font_bold_paths = ["arialbd.ttf", "fonts/IBMPlexSans-Bold.ttf"]
            font_reg_paths = ["arial.ttf", "fonts/IBMPlexSans-Regular.ttf"]
            font_icon_paths = ["fonts/RedditIcons.ttf", "fonts/DejaVuSans.ttf", "arial.ttf"] 

            title_font = load_font(font_bold_paths, 32)  # Increased from 24
            info_font_bold = load_font(font_bold_paths, 22)  # Increased from 18
            info_font_reg = load_font(font_reg_paths, 22)  # Increased from 18
            link_font = load_font(font_reg_paths, 20)  # Increased from 16
            action_button_font = load_font(font_bold_paths, 20)  # Increased from 16
            symbol_font = load_font(font_icon_paths, 22)  # Increased from 18  
            
            # --- ASSETS ---
            # Mock assets_dir for testing
            assets_dir = "assets"
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
                print(f"Created mock 'assets' directory. Please add icon files there.")

            # 1. Subreddit Logo
            logo_path = os.path.join(assets_dir, "reddit_logo.png") 
            logo_img = None
            logo_size = 50 * scale
            if os.path.exists(logo_path):
                try:
                    logo_img = Image.open(logo_path).convert('RGBA').resize((logo_size, logo_size), Image.LANCZOS)
                    logo_mask = Image.new('L', (logo_size, logo_size), 0)
                    ImageDraw.Draw(logo_mask).ellipse((0, 0, logo_size, logo_size), fill=255)
                    logo_img.putalpha(logo_mask)
                except Exception as e:
                    print(f"Error loading logo: {e}")

            # 2. Action Icons
            icon_size = 18 * scale
            
            def get_icon(name, fallback_unicode=""):
                icon_file = os.path.join(assets_dir, f"icon_{name}.png")
                if os.path.exists(icon_file):
                    try:
                        img = Image.open(icon_file).convert('RGBA').resize((icon_size, icon_size), Image.LANCZOS)
                        
                        # Colorize icons to white for black theme
                        if card_style == "black":
                            # Create white version of icon
                            img_array = img.copy()
                            pixels = img_array.load()
                            for i in range(img_array.width):
                                for j in range(img_array.height):
                                    r, g, b, a = pixels[i, j]
                                    if a > 0:  # Only modify non-transparent pixels
                                        pixels[i, j] = (colors["button_fg"][0], colors["button_fg"][1], colors["button_fg"][2], a)
                            return img_array
                        return img
                    except Exception as e:
                        print(f"Error loading icon {icon_file}: {e}")
                return fallback_unicode 

            # Load all action icons
            icon_upvote = get_icon("upvote", "↑")
            icon_downvote = get_icon("downvote", "↓")
            icon_comment = get_icon("comment", "💬")
            icon_share = get_icon("share", "🔗")
            icon_save = get_icon("save", "🔖")
            
            # Load arrow icons (can be larger than action icons)
            arrow_size = 20 * scale
            icon_arrow_up = None
            icon_arrow_down = None

            arrow_up_file = os.path.join(assets_dir, "icon_upvote.png")
            if os.path.exists(arrow_up_file):
                try:
                    icon_arrow_up = Image.open(arrow_up_file).convert('RGBA').resize((arrow_size, arrow_size), Image.LANCZOS)
                    
                    # Colorize up arrow (accent color for upvote)
                    if card_style == "black":
                        pixels = icon_arrow_up.load()
                        for i in range(icon_arrow_up.width):
                            for j in range(icon_arrow_up.height):
                                r, g, b, a = pixels[i, j]
                                if a > 0:
                                    pixels[i, j] = (colors["accent"][0], colors["accent"][1], colors["accent"][2], a)
                except Exception as e:
                    print(f"Error loading arrow_up: {e}")

            arrow_down_file = os.path.join(assets_dir, "icon_downvote.png")
            if os.path.exists(arrow_down_file):
                try:
                    icon_arrow_down = Image.open(arrow_down_file).convert('RGBA').resize((arrow_size, arrow_size), Image.LANCZOS)
                    
                    # Colorize down arrow (muted color)
                    if card_style == "black":
                        pixels = icon_arrow_down.load()
                        for i in range(icon_arrow_down.width):
                            for j in range(icon_arrow_down.height):
                                r, g, b, a = pixels[i, j]
                                if a > 0:
                                    pixels[i, j] = (colors["muted"][0], colors["muted"][1], colors["muted"][2], a)
                except Exception as e:
                    print(f"Error loading arrow_down: {e}")

            # --- LAYOUT & DRAWING ---
            cx = ss_padding
            cy = ss_padding
            content_right_edge = ss_width - ss_padding
            content_bottom_edge = ss_height - ss_padding
            
            # ----------------------------------------------------
            # 1. THUMBNAIL AREA (Right Side)
            # ----------------------------------------------------
            # thumb_w = 160 * scale  # Wider thumbnail
            # thumb_h = 100 * scale  # Taller thumbnail
            
            # thumb_x = content_right_edge - thumb_w  
            # thumb_y = (ss_height - thumb_h) // 2  # Center vertically in card
            
            # draw.rounded_rectangle([(thumb_x, thumb_y), (content_right_edge, thumb_y + thumb_h)],  
            #                      radius=6 * scale, fill=colors["muted"])

            # ----------------------------------------------------
            # 2. HEADER (Top Left)
            # ----------------------------------------------------
            logo_y = cy
            if logo_img:
                base.paste(logo_img, (cx, logo_y), logo_img)
                header_x = cx + logo_size + (15 * scale)  # More space after logo
            else:
                header_x = cx
                logo_size = 0 # Ensure logo_size is 0 if no image

            subreddit = f"r/{reddit_info.get('subreddit', 'NoStupidQuestions')}"
            time_ago = reddit_info.get('time_ago', '')
            popularity = reddit_info.get('popularity', 'Popular on Reddit right now')
            
            draw.text((header_x, logo_y + 2 * scale), subreddit, fill=colors["title"], font=info_font_bold)
            
            bbox_sub = draw.textbbox((0, 0), subreddit, font=info_font_bold)
            current_x_header = header_x + (bbox_sub[2] - bbox_sub[0]) + (20 * scale)  # Much more space after subreddit
            
            header_info_line = f"  •  {time_ago}  •  {popularity}"  # Added spaces around bullets
            draw.text((current_x_header, logo_y + 2 * scale), header_info_line, fill=colors["muted"], font=info_font_reg)

            # Draw JOIN Button (top right)
            button_text = "Join"
            btn_padding_x, btn_padding_y = 18 * scale, 10 * scale  # Increased from 15, 8
            bbox_btn_text = draw.textbbox((0,0), button_text, font=info_font_bold)
            btn_text_w = bbox_btn_text[2] - bbox_btn_text[0]
            btn_w = btn_text_w + btn_padding_x * 2
            btn_h = bbox_btn_text[3] - bbox_btn_text[1] + btn_padding_y * 2
            
            btn_x = content_right_edge - btn_w
            btn_y = cy  
            
            draw.rounded_rectangle([(btn_x, btn_y), (content_right_edge, btn_y + btn_h)],  
                                 radius=btn_h // 2, fill=colors["join_button_bg"])
            draw.text((btn_x + btn_padding_x, btn_y + btn_padding_y),  
                      button_text, fill=colors["join_button_fg"], font=info_font_bold)

            # ----------------------------------------------------
            # 3. TITLE & LINK (Middle Left)
            # ----------------------------------------------------
            # Use max of logo_size or btn_h to clear header
            header_bottom = cy + max(logo_size, btn_h) 
            title_start_y = header_bottom + (28 * scale)  # Increased from 20 for more spacing
            content_limit_x = content_right_edge - (ss_padding * 2)  # Use almost full width
            
            title = reddit_info.get('original_title', 'Why are there so many "lady-boys" in Thailand?')
            
            def wrap_text(text, font, max_width):
                words, lines = text.split(), []
                current_line = ""
                for word in words:
                    test_line = current_line + word + " "
                    # Check width *without* trailing space for more accurate wrapping
                    if draw.textbbox((0, 0), test_line.rstrip(), font=font)[2] <= max_width:
                        current_line = test_line
                    else:
                        lines.append(current_line.strip())
                        current_line = word + " "
                lines.append(current_line.strip())
                return lines

            title_lines = wrap_text(title, title_font, content_limit_x - cx)
            title_line_h = draw.textbbox((0, 0), "Ag", font=title_font)[3] + (15 * scale)  # Increased from 10 to 15
            
            for i, line in enumerate(title_lines):
                draw.text((cx, title_start_y + i * title_line_h), line, fill=colors["title"], font=title_font)
                
            link = reddit_info.get('url', '')
            link_y = title_start_y + min(2, len(title_lines)) * title_line_h + (12 * scale)  # Increased from 8 to 12
            draw.text((cx, link_y), link, fill=colors["link"], font=link_font)

            # ----------------------------------------------------
            # 4. FOOTER ACTIONS (Bottom Left - Capsule Buttons)
            # ----------------------------------------------------
            
            # --- HELPER: draw_capsule_button (icon + text in rounded capsule) ---
            def draw_capsule_button(start_x, text, icon_obj, center_y, is_active=False):
                # Determine colors
                if is_active:
                    bg_color = colors["button_active_bg"]
                    fg_color = colors["button_active_fg"]
                else:
                    bg_color = colors["button_bg"]
                    fg_color = colors["button_fg"]
                
                # Button padding - INCREASED
                btn_pad_x = 18 * scale  # Was 12
                btn_pad_y = 8 * scale  # Was 8
                icon_text_gap = 12 * scale  # Was 6
                
                # Get icon dimensions
                icon_h = 18 * scale
                if isinstance(icon_obj, Image.Image):
                    icon_w = icon_obj.width
                else:
                    bbox_icon = draw.textbbox((0,0), icon_obj, font=symbol_font)
                    icon_w = bbox_icon[2] - bbox_icon[0]
                    icon_h = bbox_icon[3] - bbox_icon[1]
                
                # Get text dimensions
                bbox_text = draw.textbbox((0,0), text, font=action_button_font)
                text_w = bbox_text[2] - bbox_text[0]
                text_h = bbox_text[3] - bbox_text[1]
                
                # Calculate button dimensions
                btn_content_w = icon_w + icon_text_gap + text_w
                btn_w = btn_content_w + btn_pad_x * 2
                btn_h = max(icon_h, text_h) + btn_pad_y * 2
                
                # Button position
                btn_x = start_x
                btn_y = center_y - (btn_h // 2)
                
                # Draw capsule background
                draw.rounded_rectangle(
                    [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
                    radius=btn_h // 2,
                    fill=bg_color
                )
                
                # Draw icon
                icon_x = btn_x + btn_pad_x
                icon_y = btn_y + (btn_h - icon_h) // 2
                
                if isinstance(icon_obj, Image.Image):
                    base.paste(icon_obj, (icon_x, icon_y), icon_obj)
                else:
                    draw.text((icon_x, icon_y), icon_obj, fill=fg_color, font=symbol_font)
                
                # Draw text
                text_x = icon_x + icon_w + icon_text_gap
                text_y = btn_y + (btn_h - text_h) // 2
                draw.text((text_x, text_y), text, fill=fg_color, font=action_button_font)
                
                # Return X for next button
                return btn_x + btn_w + (30 * scale)  # Increased from 25 to 30
            
            # --- End of helper ---

            # Calculate a common vertical center for all footer items
            bbox_score = draw.textbbox((0,0), "1.9k", font=info_font_bold)
            score_h = bbox_score[3] - bbox_score[1]
            
            # Align center with middle of content area - adjusted for larger fonts
            footer_center_y = content_bottom_edge - (score_h // 2) + (22 * scale)   # Increased from 17 to 22

            current_x = cx
            
            # --- 1. Upvote/Downvote Capsule ---
            upvotes = reddit_info.get('upvotes', 3500)
            upvotes_formatted = self._format_number(upvotes)
            
            # Create capsule for vote block
            btn_pad_x = 18 * scale  # Increased from 15
            btn_pad_y = 10 * scale  # Increased from 8
            
            # Calculate dimensions
            if icon_arrow_up and icon_arrow_down:
                arrow_w = arrow_size
                arrow_h = arrow_size
            else:
                arrow_w, arrow_h = 16 * scale, 12 * scale
            
            bbox_score_text = draw.textbbox((0,0), upvotes_formatted, font=info_font_bold)
            score_text_w = bbox_score_text[2] - bbox_score_text[0]
            score_text_h = bbox_score_text[3] - bbox_score_text[1]
            
            # Vote capsule dimensions - MORE SPACING
            vote_content_w = arrow_w + (10 * scale) + score_text_w + (5 * scale) + arrow_w  # Was 5*scale
            vote_btn_w = vote_content_w + btn_pad_x * 2
            vote_btn_h = max(arrow_h, score_text_h) + btn_pad_y * 2
            
            vote_btn_x = current_x
            vote_btn_y = footer_center_y - (vote_btn_h // 2)
            
            # Draw vote capsule background
            draw.rounded_rectangle(
                [(vote_btn_x, vote_btn_y), (vote_btn_x + vote_btn_w, vote_btn_y + vote_btn_h)],
                radius=vote_btn_h // 2,
                fill=colors["button_bg"]
            )
            
            # Draw arrows and score inside capsule
            content_start_x = vote_btn_x + btn_pad_x
            
            if icon_arrow_up and icon_arrow_down:
                # Up Arrow Icon
                up_arrow_x = content_start_x
                up_arrow_y = vote_btn_y + (vote_btn_h - arrow_h) // 2
                base.paste(icon_arrow_up, (up_arrow_x, up_arrow_y), icon_arrow_up)
                
                # Score Text - MORE SPACING
                score_x = up_arrow_x + arrow_w + (10 * scale)  # Was 5
                score_y = vote_btn_y + (vote_btn_h - score_text_h) // 2
                draw.text((score_x, score_y), upvotes_formatted, fill=colors["title"], font=info_font_bold)
                
                # Down Arrow Icon
                down_arrow_x = score_x + score_text_w + (10 * scale)  # Was 5
                down_arrow_y = up_arrow_y
                base.paste(icon_arrow_down, (down_arrow_x, down_arrow_y), icon_arrow_down)
            else:
                # Fallback triangles
                up_arrow_x = content_start_x
                up_arrow_top_y = vote_btn_y + (vote_btn_h - arrow_h) // 2
                up_center_x = up_arrow_x + arrow_w // 2
                up_triangle = [(up_center_x, up_arrow_top_y), 
                               (up_arrow_x, up_arrow_top_y + arrow_h), 
                               (up_arrow_x + arrow_w, up_arrow_top_y + arrow_h)]
                draw.polygon(up_triangle, fill=colors["accent"])
                
                # Score Text - increased spacing
                score_x = up_arrow_x + arrow_w + (7 * scale)  # Increased from 5 to 7
                score_y = vote_btn_y + (vote_btn_h - score_text_h) // 2
                draw.text((score_x, score_y), upvotes_formatted, fill=colors["title"], font=info_font_bold)
                
                # Down Arrow
                down_arrow_x = score_x + score_text_w + (7 * scale)  # Increased from 5 to 7
                down_arrow_top_y = up_arrow_top_y
                down_center_x = down_arrow_x + arrow_w // 2
                down_triangle = [(down_center_x, down_arrow_top_y + arrow_h), 
                                 (down_arrow_x, down_arrow_top_y), 
                                 (down_arrow_x + arrow_w, down_arrow_top_y)]
                draw.polygon(down_triangle, fill=colors["muted"])
            
            # Advance current_x - increased spacing between buttons
            current_x = vote_btn_x + vote_btn_w + (30 * scale)  # Increased from 25 to 30

            # --- 2. Comments Capsule Button ---
            comments = reddit_info.get('comments', 1900)
            comments_formatted = self._format_number(comments)
            current_x = draw_capsule_button(current_x, f"{comments_formatted} Comments", icon_comment, footer_center_y)

            # --- 3. Share Capsule Button ---
            current_x = draw_capsule_button(current_x, "Share", icon_share, footer_center_y)
            
            # --- 4. Save Capsule Button ---
            draw_capsule_button(current_x, "Save", icon_save, footer_center_y)
            
            # --- FINALIZATION ---
            # Resize down with antialiasing for a high-quality result
            final_size = (card_width, card_height)  # No extra margin
            base = base.resize(final_size, Image.LANCZOS)
            
            if not os.path.exists(output_path):
                os.makedirs(output_path)
                
            card_path = os.path.join(output_path, f"reddit_card_link_{int(time.time())}.png")
            base.save(card_path, "PNG")

            # Calculate reading time based on title length
            # Average reading speed: ~200 words per minute = 3.3 words per second
            # We'll use a more conservative 2.5 words per second for comfortable reading
            # Plus add extra time for longer titles
            word_count = len(title.split())
            reading_time = max(3.0, word_count / 2.5)  # Minimum 3 seconds, then 2.5 words/sec
            # Add a bit of extra time for longer titles (people read slower with more text)
            if word_count > 15:
                reading_time += 1.0

            print(f"✅ Reddit Link Card created: {card_path}")
            print(f"   Title: {word_count} words, Reading time: {reading_time:.1f}s")
            return card_path, reading_time

        except Exception as e:
            import traceback
            print(f"❌ Error creating Reddit card: {e}")
            print(traceback.format_exc())
            return None, 3.0  # Return default reading time on error
    
    def _format_number(self, num: int) -> str:
        """Formats numbers like Reddit (1.2k, 5.3k, etc.)"""
        if num >= 1000:
            return f"{num/1000:.1f}k"
        return str(num)
    
    def _adjust_subtitle_speed(self, subtitle_file: str, speed: float) -> str:
        """Adjusts subtitle timing to match video speed."""
        try:
            import pysubs2
            
            print(f"⚡ Adjusting subtitle timing for {speed}x speed...")
            
            # Load subtitles (works for both SRT and ASS)
            subs = pysubs2.load(subtitle_file)
            
            # Adjust all timestamps (divide by speed to match faster video)
            for line in subs:
                line.start = int(line.start / speed)
                line.end = int(line.end / speed)
            
            # Determine file extension
            file_ext = '.ass' if subtitle_file.endswith('.ass') else '.srt'
            
            # Save adjusted subtitles with same format
            adjusted_file = subtitle_file.replace(file_ext, f'_speed{speed}{file_ext}')
            subs.save(adjusted_file)
            
            print(f"✅ Subtitles adjusted: {adjusted_file}")
            return adjusted_file
            
        except Exception as e:
            print(f"⚠️ Failed to adjust subtitle speed: {e}, using original")
            return subtitle_file
        
    def create_video_ffmpeg(self, content: Dict, audio_path: str, background_path: str, background_music_path: str = None, subtitle_style: str = None, card_style: str = "white", card_animation: str = "slide") -> str:
        """Creates video using FFmpeg directly - MUCH faster than MoviePy."""
        print("🚀 Creating video with FFmpeg (ultra-fast)...")
        
        try:
            # Get audio duration
            probe = ffmpeg.probe(audio_path)
            audio_duration = float(probe['streams'][0]['duration'])
            print(f"📏 Audio duration: {audio_duration:.2f}s")
            
            # Create output filename
            safe_title = self._make_safe_filename(content['title'])
            output_file = os.path.join(self.output_path, f"{safe_title}_{int(time.time())}.mp4")
            
            # Step 1: Extract random segment from background video
            probe_video = ffmpeg.probe(background_path)
            video_duration = float(probe_video['streams'][0]['duration'])
            
            if video_duration > audio_duration:
                # Random start time
                import random
                max_start = video_duration - audio_duration
                start_time = random.uniform(0, max_start)
                print(f"🎲 Random segment starting at {start_time:.1f}s")
            else:
                start_time = 0
            
            # Step 2: Create subtitle file using user-selected style (or config default)
            subtitle_file = self._create_srt_subtitles(content["story"], audio_duration, audio_path, subtitle_style)
            
            # Step 2.5: Create Reddit card if available with user-selected style
            reddit_card_path = None
            card_reading_time = 3.0  # Default
            if 'reddit_info' in content and content['reddit_info']:
                print(f"🎴 Creating Reddit card overlay (style: {card_style})...")
                reddit_card_path, card_reading_time = self._create_reddit_card(content['reddit_info'], self.output_path, card_style)
                if reddit_card_path:
                    print(f"✅ Reddit card created at: {reddit_card_path}")
                else:
                    print(f"⚠️ Reddit card creation failed")
            else:
                print(f"ℹ️ No Reddit info found, skipping card overlay")
            
            # Step 3: Create video with FFmpeg (crop + subtitles + audio)
            input_video = ffmpeg.input(background_path, ss=start_time, t=audio_duration)
            input_audio = ffmpeg.input(audio_path)
            
            # Crop to vertical format (intelligent crop to avoid stretching)
            # First get video info to calculate proper crop
            probe = ffmpeg.probe(background_path)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            width = int(video_info['width'])
            height = int(video_info['height'])
            
            # Calculate best crop for 9:16 aspect ratio without stretching
            target_ratio = 9/16  # vertical video ratio
            current_ratio = width / height
            
            if current_ratio > target_ratio:
                # Video is too wide, crop width
                new_width = int(height * target_ratio)
                crop_x = (width - new_width) // 2
                stream = ffmpeg.filter(input_video, 'crop', new_width, height, crop_x, 0)
            else:
                # Video is too tall, crop height  
                new_height = int(width / target_ratio)
                crop_y = (height - new_height) // 2
                stream = ffmpeg.filter(input_video, 'crop', width, new_height, 0, crop_y)
            
            # Scale to final size maintaining aspect ratio (use high-quality Lanczos scaler)
            stream = ffmpeg.filter(stream, 'scale', 1080, 1920, flags='lanczos')
            
            # Speed up video by 1.15x (15% faster)
            stream = ffmpeg.filter(stream, 'setpts', 'PTS/1.15')
            
            # Adjust subtitle timing to match 1.15x speed if we have subtitles
            if subtitle_file:
                subtitle_file = self._adjust_subtitle_speed(subtitle_file, 1.15)
            
            # Add subtitles with FFmpeg - optimized for mobile viewing
            if subtitle_file:
                print(f"📝 Adding speed-adjusted subtitles from: {subtitle_file}")
                
                # Check if using ASS format (3-word highlight style)
                if subtitle_file.endswith('.ass'):
                    # ASS format with custom styling already embedded
                    # Need to escape the path for FFmpeg on Windows
                    escaped_path = subtitle_file.replace('\\', '\\\\').replace(':', '\\:')
                    print(f"🎨 Using ASS format with 3-word highlighting: {escaped_path}")
                    stream = ffmpeg.filter(stream, 'subtitles', escaped_path)
                else:
                    # SRT format - apply FFmpeg subtitle filter with styling
                    # Dynamic word-by-word subtitles - smaller size, Luckiest Guy style font
                    # Font fallbacks: Cooper Black -> Balloon -> Impact -> Arial Black (similar to Luckiest Guy)
                    stream = ffmpeg.filter(stream, 'subtitles', subtitle_file, 
                                         force_style='FontName=Cooper Black,FontSize=20,PrimaryColour=&H00ffff,OutlineColour=&H000000,Outline=2,Shadow=0,Bold=1,Alignment=2,MarginV=80,Spacing=0')
            
            # Add Reddit card overlay if reddit_info exists
            if reddit_card_path and os.path.exists(reddit_card_path):
                print(f"🎴 Adding Reddit card overlay to video...")
                print(f"   Card path: {reddit_card_path}")
                print(f"   Card exists: {os.path.exists(reddit_card_path)}")
                try:
                    # Use dynamic reading time based on title length (adjusted for 1.15x speed)
                    card_duration = min(card_reading_time / 1.15, audio_duration / 1.15)
                    card_input = ffmpeg.input(reddit_card_path, loop=1, t=card_duration)
                    
                    # Target Y position (150px above center)
                    overlay_y_target = '(H-h)/2-150'
                    
                    if card_animation == "zoom":
                        # ZOOM-IN ANIMATION: Simplified approach using scale with time-based expression
                        print(f"🔍 Using zoom-in animation (simplified scaling)")
                        
                        zoom_duration = 0.8
                        
                        # Much simpler scale expression that FFmpeg can handle
                        # Scale from 0.7 to 1.0 over zoom_duration
                        scale_progress = f'min(t/{zoom_duration}, 1.0)'
                        scale_factor = f'0.7 + 0.3 * {scale_progress}'
                        
                        # Apply scaling with simplified expression
                        card_scaled = card_input.filter(
                            'scale',
                            w=f'iw*({scale_factor})',
                            h=f'ih*({scale_factor})',
                            eval='frame'
                        )
                        
                        # Simple centered positioning - let FFmpeg handle the centering
                        x_expr = '(W-w)/2'
                        y_expr = overlay_y_target
                        
                        print(f"[FFmpeg overlay] Simplified scale animation (0.7→1.0), duration={card_duration:.1f}s")
                        
                    else:
                        # SLIDE-IN ANIMATION: Card slides up from bottom with wobble (default)
                        print(f"📈 Using slide-in animation")
                        
                        # Scale with high-quality Lanczos algorithm, maintaining aspect ratio
                        card_scaled = card_input
                        
                        # Animation timing
                        slide_duration = 0.8  # Slide takes 0.8 seconds
                        wobble_start = 0.8    # Wobble starts after slide
                        freeze_t = 1.4        # Total animation time
                        
                        # Cubic ease-out: progress = 1 - pow(1 - t/duration, 3)
                        # Start position is H (bottom of screen), end is target
                        slide_progress = f'min(t/{slide_duration}, 1.0)'
                        eased = f'(1 - pow(1 - {slide_progress}, 3))'
                        slide_y = f'H - (H - ({overlay_y_target})) * {eased}'
                        
                        # Gentle wobble after slide (only when t > wobble_start)
                        wobble_t = f'(t - {wobble_start})'
                        wobble_amplitude = 40
                        wobble_decay = 6.0
                        wobble_freq = 2.5
                        wobble = f'if(gt(t, {wobble_start}), {wobble_amplitude} * exp(-{wobble_decay}*{wobble_t}) * sin(2*PI*{wobble_freq}*{wobble_t}), 0)'
                        
                        # Combined: slide + wobble, then freeze
                        animated_expr = f'{slide_y} + {wobble}'
                        y_expr = f'if(lt(t,{freeze_t}), {animated_expr}, ({overlay_y_target}))'
                        x_expr = '(W-w)/2'
                        
                        print(f"[FFmpeg overlay] Slide-in with wobble, duration={card_duration:.1f}s")

                    stream = ffmpeg.overlay(
                        stream, card_scaled,
                        x=x_expr,
                        y=y_expr,
                        enable=f'between(t,0,{card_duration})'
                    )
                    print(f"✅ Reddit card overlay added ({card_animation} animation, {card_reading_time:.1f}s reading time)")
                except Exception as overlay_error:
                    print(f"❌ Failed to add overlay: {overlay_error}")
                    import traceback
                    print(f"🔍 Overlay traceback: {traceback.format_exc()}")
            else:
                print(f"⚠️ Reddit card not available for overlay")
                if reddit_card_path:
                    print(f"   Path exists check: {os.path.exists(reddit_card_path)}")
            
            # Speed up audio by 1.15x (15% faster) to match video
            audio_stream = ffmpeg.filter(input_audio, 'atempo', 1.15)

            # Add ding sound effect at the start
            final_audio = audio_stream
            sfx_dir = os.path.join(os.path.dirname(__file__), 'soundeffects')
            
            try:
                # Add ding at the very beginning
                ding_path = os.path.join(sfx_dir, 'ding.mp3')
                if os.path.exists(ding_path):
                    print(f"🔔 Adding ding sound effect at start")
                    ding_input = ffmpeg.input(ding_path)
                    # Process ding - match tempo and boost volume
                    ding_proc = ffmpeg.filter(ding_input, 'atempo', 1.15)
                    ding_proc = ffmpeg.filter(ding_proc, 'aformat', channel_layouts='mono')
                    ding_proc = ffmpeg.filter(ding_proc, 'volume', 3.0)
                    # Mix ding with main audio at the start
                    mixed_audio = ffmpeg.filter([audio_stream, ding_proc], 'amix', inputs=2, duration='longest', dropout_transition=0)
                    final_audio = mixed_audio
                else:
                    print("⚠️ Ding sound effect not found at ./soundeffects/ding.mp3")
            except Exception as ding_err:
                print(f"⚠️ Could not add ding SFX: {ding_err}")

            # Optionally mix a swish SFX when the card slides in
            try:
                swish_candidates = [
                    os.path.join(sfx_dir, 'swish1.mp3'),
                    os.path.join(sfx_dir, 'swish2.mp3'),
                ]
                swish_candidates = [p for p in swish_candidates if os.path.exists(p)]
                if swish_candidates and reddit_card_path:
                    chosen_swish = random.choice(swish_candidates)
                    print(f"🔊 Adding swish SFX: {os.path.basename(chosen_swish)}")
                    swish_input = ffmpeg.input(chosen_swish)
                    # Match overall tempo and make it clearly audible, slightly after movement starts
                    swish_proc = ffmpeg.filter(swish_input, 'atempo', 1.15)
                    # Ensure channel layout matches (mixing is simpler in mono)
                    swish_proc = ffmpeg.filter(swish_proc, 'aformat', channel_layouts='mono')
                    # Boost volume so it cuts through narration
                    
                    swish_proc = ffmpeg.filter(swish_proc, 'volume', 6.0)
                    # Mix swish with the audio (which now includes ding)
                    mixed_audio = ffmpeg.filter([final_audio, swish_proc], 'amix', inputs=2, duration='longest', dropout_transition=0)
                    final_audio = mixed_audio
                else:
                    if not swish_candidates:
                        print("ℹ️ No swish SFX files found in ./soundeffects (swish1.mp3/swish2.mp3)")
            except Exception as sfx_err:
                print(f"⚠️ Could not mix swish SFX: {sfx_err}")
            
            # Add background music if provided
            if background_music_path and os.path.exists(background_music_path):
                try:
                    print(f"🎵 Adding background music: {os.path.basename(background_music_path)}")
                    adjusted_video_duration = audio_duration / 1.15  # Account for 1.15x speed change
                    
                    # Build background music pipeline with robust fallback
                    def build_music(loop: bool):
                        src = ffmpeg.input(background_music_path, **({'stream_loop': -1} if loop else {}))
                        proc = ffmpeg.filter(src, 'atempo', 1.15)
                        # If not looping, pad with silence then trim to exact duration
                        if not loop:
                            proc = ffmpeg.filter(proc, 'apad')
                        proc = ffmpeg.filter(proc, 'atrim', end=adjusted_video_duration)
                        proc = ffmpeg.filter(proc, 'asetpts', 'PTS-STARTPTS')
                        proc = ffmpeg.filter(proc, 'volume', 0.4)
                        proc = ffmpeg.filter(proc, 'afade', t='in', st=0, d=2)
                        fade_start_inner = max(0, adjusted_video_duration - 3)
                        proc = ffmpeg.filter(proc, 'afade', t='out', st=fade_start_inner, d=3)
                        proc = ffmpeg.filter(proc, 'aformat', channel_layouts='mono')
                        proc = ffmpeg.filter(proc, 'aresample', **{'async': 1})
                        return proc

                    try:
                        music_proc = build_music(loop=True)
                    except Exception as loop_err:
                        print(f"🔁 stream_loop failed or unsupported, retrying without loop + apad: {loop_err}")
                        music_proc = build_music(loop=False)
                    
                    # Mix background music with the final audio (narration + swish)
                    final_audio = ffmpeg.filter(
                        [final_audio, music_proc], 
                        'amix', 
                        inputs=2, 
                        duration='shortest',
                        dropout_transition=0
                    )
                    print("✅ Background music mixed successfully")
                    
                except Exception as music_err:
                    print(f"⚠️ Could not add background music: {music_err}")
                    import traceback
                    print(f"🔍 Music error traceback: {traceback.format_exc()}")
            else:
                if background_music_path:
                    print(f"⚠️ Background music file not found: {background_music_path}")
                else:
                    print("ℹ️ No background music selected")
            
            # Add audio and output with improved quality settings
            # - Use CRF-based quality (no low bitrate cap)
            # - Higher audio bitrate for clarity
            # - High profile for better compression efficiency
            # - faststart for better upload/streaming compatibility
            output = ffmpeg.output(
                stream, final_audio, output_file,
                vcodec='libx264', acodec='aac',
                preset='medium', crf=19,
                pix_fmt='yuv420p',
                profile='high', level='4.1',
                movflags='+faststart',
                r=30, g=60,  # 30fps target with 2s GOP
                maxrate='8M', bufsize='16M',  # allow higher peaks while staying upload-friendly
                **{'b:a': '160k'}
            )
            
            # Run FFmpeg
            print("⚡ Running FFmpeg with subtitles and overlay...")
            try:
                # Capture stdout/stderr for better error diagnostics
                ffmpeg.run(output, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            except ffmpeg.Error as fe:
                # Print detailed ffmpeg stderr to help diagnose filter/codec issues
                try:
                    err_text = fe.stderr.decode('utf-8', errors='ignore') if hasattr(fe, 'stderr') else str(fe)
                except Exception:
                    err_text = str(fe)
                cmd_text = " ".join(getattr(fe, 'cmd', [])) if hasattr(fe, 'cmd') else ''
                print("❌ FFmpeg failed. Command:", cmd_text)
                print("── FFmpeg stderr (start) ──")
                print(err_text)
                print("── FFmpeg stderr (end) ──")
                # Re-raise to be caught by outer handler
                raise
            
            # Clean up temporary files
            if subtitle_file and os.path.exists(subtitle_file):
                os.remove(subtitle_file)
                # Also remove speed-adjusted subtitle if it exists
                for ext in ['.srt', '.ass']:
                    adjusted_sub = subtitle_file.replace(ext, f'_speed1.15{ext}')
                    if os.path.exists(adjusted_sub):
                        os.remove(adjusted_sub)
            
            # Keep reddit card for debugging (comment out to keep)
            if reddit_card_path and os.path.exists(reddit_card_path):
                print(f"ℹ️ Reddit card kept at: {reddit_card_path} (for debugging)")
                # os.remove(reddit_card_path)  # Uncomment to remove
            
            
            print(f"✅ Video created with FFmpeg: {output_file}")
            return output_file
            
        except Exception as e:
            print(f"❌ FFmpeg processing failed: {e}")
            return None
    
    def _create_srt_subtitles(self, story: str, total_duration: float, audio_path: str, subtitle_style: str = None) -> str:
        """Creates word-by-word SRT subtitle file using Whisper for precise timing."""
        try:
            import whisper
            import pysubs2
            import re
            
            # Try to use Whisper for precise timing
            print("🎯 Using Whisper for precise subtitle timing...")
            
            # Load Whisper model (tiny for speed)
            model = whisper.load_model("tiny")
            
            # Transcribe with word-level timestamps
            result = model.transcribe(audio_path, word_timestamps=True)
            
            # Use provided style or fall back to config
            if subtitle_style is None:
                subtitle_style = self.config.get("subtitle_style", "single_word")
            print(f"📋 Subtitle style: {subtitle_style}")
            
            if subtitle_style == "three_words_highlight":
                print("✨ Creating 3-word highlight subtitles...")
                return self._create_three_word_highlight_subtitles(result, audio_path)
            else:
                print("📝 Creating single-word subtitles...")
                return self._create_single_word_subtitles(result, audio_path)
            
        except Exception as e:
            print(f"❌ Whisper failed ({e}). Subtitles will be skipped.")
            return None
    
    def _create_single_word_subtitles(self, whisper_result: dict, audio_path: str) -> str:
        """Creates single word at a time subtitles with grow animation (ease-out)."""
        import pysubs2
        
        # Create subtitle file - use ASS format for animation support
        subtitle_file = os.path.join(self.output_path, f"temp_subtitles_{int(time.time())}.ass")
        subs = pysubs2.SSAFile()
        
        # Configure ASS style for animation
        style = subs.styles["Default"]
        style.fontname = "Cooper Black"
        style.fontsize = 14
        style.bold = True
        style.italic = False
        style.underline = False
        style.strikeout = False
        style.scalex = 100.0
        style.scaley = 100.0
        style.spacing = 0.0
        style.angle = 0.0
        style.borderstyle = 1
        style.outline = 1
        style.shadow = 1
        style.alignment = 2  # Bottom center
        style.marginl = 10
        style.marginr = 10
        style.marginv = 100
        
        # Extract words with timestamps from Whisper result
        for segment in whisper_result["segments"]:
            if "words" in segment:
                for word_info in segment["words"]:
                    start_time = word_info["start"] * 1000  # Convert to milliseconds
                    end_time = word_info["end"] * 1000
                    word_text = word_info["word"].strip().upper()
                    
                    # Calculate animation duration (200ms = 0.2 seconds - shorter for quick bump)
                    anim_duration = 200
                    anim_end = min(start_time + anim_duration, end_time)
                    
                    # Create ease-out animation (fast start, slow end)
                    # Subtle scale: 85% to 100% (only 15% change instead of 50%)
                    # This keeps the "bump" effect but prevents words from being too big
                    
                    # Animation: scale from 85 to 100 with acceleration factor of 3 (ease-out)
                    animation = f"{{\\t(0,{anim_duration},2,\\fscx100\\fscy100)}}"

                    # Start at 92% scale
                    text_with_anim = f"{{\\fscx92\\fscy92}}{animation}{word_text}"
                    
                    # Create subtitle event
                    event = pysubs2.SSAEvent(start=int(start_time), end=int(end_time), text=text_with_anim)
                    subs.append(event)
        
        # Save ASS file
        subs.save(subtitle_file)
        print(f"✅ Single-word animated subtitles created: {len(subs)} words")
        return subtitle_file
    
    def _create_three_word_highlight_subtitles(self, whisper_result: dict, audio_path: str) -> str:
        """Creates 3-word group subtitles with highlighting shifting between words in each group."""
        import pysubs2
        
        # Create subtitle file - use ASS format for color support
        subtitle_file = os.path.join(self.output_path, f"temp_subtitles_{int(time.time())}.ass")
        subs = pysubs2.SSAFile()
        
        # Configure ASS style for better appearance
        style = subs.styles["Default"]
        style.fontname = "Cooper Black"  # Bold, impactful font
        style.fontsize = 14
        style.bold = True
        style.italic = False
        style.underline = False
        style.strikeout = False
        style.scalex = 100.0
        style.scaley = 100.0
        style.spacing = 0.0
        style.angle = 0.0
        style.borderstyle = 0  # No border
        style.outline = 0  # No outline
        style.shadow = 1  # Slight shadow
        style.alignment = 2  # Bottom center
        style.marginl = 10
        style.marginr = 10
        style.marginv = 100  # Distance from bottom
        
        # Collect all words from Whisper result
        all_words = []
        for segment in whisper_result["segments"]:
            if "words" in segment:
                for word_info in segment["words"]:
                    all_words.append({
                        "text": word_info["word"].strip().upper(),
                        "start": word_info["start"] * 1000,  # ms
                        "end": word_info["end"] * 1000  # ms
                    })
        
        # Group words into sets of 3
        # For each word in a group, create subtitle with that word highlighted
        for i in range(0, len(all_words), 3):
            # Get the 3-word group
            group = all_words[i:i+3]
            
            # Skip if group is empty
            if not group:
                continue
            
            # Pad group with empty strings if less than 3 words
            while len(group) < 3:
                group.append({"text": "", "start": group[-1]["end"], "end": group[-1]["end"]})
            
            # Calculate group timing - subtitle should be visible from first word start to last word end
            group_start = group[0]["start"]
            group_end = group[-1]["end"]
            
            # Create subtitle events for each word in the group
            # Each event shows all 3 words but highlights sync with actual word timing
            for word_idx, word in enumerate(group):
                if not word["text"]:  # Skip empty padding words
                    continue
                
                # Build 3-word text with current word highlighted in yellow
                # ASS color format: {\c&HBBGGRR&} where BB=blue, GG=green, RR=red
                # Yellow = &H00FFFF& (blue=00, green=FF, red=FF)
                # Light blue = &HE6D8AD&
                # White = &HFFFFFF&
                # Black outline = &H000000&
                
                subtitle_parts = []
                for idx, g_word in enumerate(group):
                    if not g_word["text"]:
                        continue
                    
                    if idx == word_idx:
                        # Current word - highlight in green (no animation)
                        # ASS color format: &HBBGGRR& where BB=blue, GG=green, RR=red
                        # Bright green = &H00FF00& (blue=00, green=FF, red=00)
                        subtitle_parts.append(f"{{\\c&H00FFFF&\\3c&H000000&}}{g_word['text']}")
                    else:
                        # Other words - white (no animation)
                        subtitle_parts.append(f"{{\\c&HFFFFFF&\\3c&H000000&}}{g_word['text']}")
                
                subtitle_text = " ".join(subtitle_parts)
                
                # Calculate timing for this highlight:
                # - Start when this word is spoken
                # - End when next word starts (or group ends for last word)
                highlight_start = word["start"]
                if word_idx < len(group) - 1 and group[word_idx + 1]["text"]:
                    # End when next word starts
                    highlight_end = group[word_idx + 1]["start"]
                else:
                    # Last word - extend to group end
                    highlight_end = group_end
                
                # Create subtitle event that spans from word start to next word start
                event = pysubs2.SSAEvent(
                    start=int(highlight_start), 
                    end=int(highlight_end), 
                    text=subtitle_text
                )
                subs.append(event)
        
        # Save with custom styling for ASS format
        subs.save(subtitle_file)
        print(f"✅ 3-word group highlight subtitles created: {len(subs)} events")
        return subtitle_file
        

    def _make_safe_filename(self, title: str) -> str:
        """Creates a filesystem-safe filename from a title."""
        import re
        safe = re.sub(r'[^\w\s-]', '', title)
        safe = re.sub(r'[-\s]+', '_', safe)
        return safe[:30]
    
    def _extract_thumbnail(self, video_path: str, timestamp: float = 2.0) -> str:
        """Extracts a thumbnail from the video at a specific timestamp."""
        try:
            print(f"📸 Extracting thumbnail at {timestamp}s...")
            
            # Create thumbnail filename
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            thumbnail_path = os.path.join(self.output_path, f"{base_name}_thumb.jpg")
            
            # Extract frame at specific timestamp using FFmpeg
            (
                ffmpeg
                .input(video_path, ss=timestamp)
                .output(thumbnail_path, vframes=1, format='image2', vcodec='mjpeg', **{'q:v': 2})
                .overwrite_output()
                .run(quiet=True)
            )
            
            if os.path.exists(thumbnail_path):
                print(f"✅ Thumbnail saved: {thumbnail_path}")
                return thumbnail_path
            else:
                print(f"❌ Thumbnail extraction failed")
                return None
                
        except Exception as e:
            print(f"❌ Thumbnail extraction error: {e}")
            return None




class InstagramUploader:
    """Handles Instagram login and video uploading."""
    def __init__(self, config: Dict):
        self.config = config.get("instagram", {})
        self.session_file = "instagram_session.json"

    def upload(self, video_path: str, thumbnail_path: str, content: Dict) -> bool:
        """Uploads a video to Instagram Reels."""
        if not Client:
            print("❌ Instagrapi library not available.")
            return False
        if not self.config.get("username"):
            print("⚠️ Instagram username not configured. Skipping upload.")
            return False

        print("📸 Attempting Instagram upload...")
        
        # Validate file
        if not os.path.exists(video_path):
            print(f"❌ Video file not found: {video_path}")
            return False
        
        cl = Client()
        if not self._login(cl):
            return False

        # Create caption with credits and required hashtags for reels
        tts_name = content.get('tts_engine', 'Edge-TTS')
        caption = f"{content['title']}\n\n{content['hashtags']} #viral #fy #reels\n\n🎙️ Voice: {tts_name}"
        
        try:
            print("🎬 Uploading as Reel...")
            if thumbnail_path and os.path.exists(thumbnail_path):
                print(f"🖼️ Using custom thumbnail: {thumbnail_path}")
                media = cl.clip_upload(video_path, caption, thumbnail=thumbnail_path)
            else:
                print("🖼️ No custom thumbnail provided - Instagram will auto-generate one")
                media = cl.clip_upload(video_path, caption)
            if media and hasattr(media, 'code'):
                print(f"✅ Successfully uploaded! Link: https://instagram.com/reel/{media.code}")
                return True
            raise Exception("Reel upload returned no media object.")
        except Exception as e:
            print(f"❌ Reel upload failed: {e}. ")

    def _login(self, cl) -> bool:
        """Handles login, including session loading and challenges."""
        if os.path.exists(self.session_file):
            try:
                cl.load_settings(self.session_file)
                # Test session with safer method - try to get own account info
                cl.account_info()
                print("✅ Instagram session is valid.")
                return True
            except KeyError as e:
                if 'data' in str(e):
                    print("⚠️ Instagram API changed - 'data' key error. Clearing session...")
                    os.remove(self.session_file)
                else:
                    print(f"⚠️ Session error: {e}. Logging in again...")
            except Exception as e:
                print(f"⚠️ Instagram session expired: {e}. Logging in again...")
        
        try:
            print("🔐 Logging into Instagram...")
            # Use more stable login method
            cl.login(self.config["username"], self.config["password"])
            
            # Wait a bit to avoid rate limiting
            import time
            time.sleep(2)
            
            cl.dump_settings(self.session_file)
            return True
        except KeyError as e:
            if 'data' in str(e):
                print("❌ Instagram 'data' KeyError - API rate limited or changed.")
                print("💡 Try again in a few minutes or use manual upload.")
                return False
            else:
                print(f"❌ Login KeyError: {e}")
                return False
        except Exception as e:
            if "challenge" in str(e).lower():
                print("📱 Instagram requires verification.")
                print("💡 Complete verification manually in Instagram app, then try again.")
                return False
            elif "Please wait a few minutes" in str(e):
                print("⏳ Instagram rate limited. Wait 10-15 minutes before trying again.")
                return False
            else:
                print(f"❌ Login failed: {e}")
                return False

class YouTubeUploader:
    """Handles YouTube API authentication and video uploading."""
    def __init__(self, client_secrets_file="client_secret.json"):
        self.client_secrets_file = client_secrets_file
        self.token_file = "youtube_token.json"
        self.scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    def _get_credentials(self):
        """Gets valid user credentials from storage or runs the OAuth2 flow."""
        creds = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"⚠️ YouTube token refresh failed: {e}. Re-authenticating...")
                    creds = None # Force re-authentication
            
            if not creds:
                if not os.path.exists(self.client_secrets_file):
                    print(f"❌ YouTube client secrets file not found: {self.client_secrets_file}")
                    print("💡 Please download it from Google Cloud Console and place it here.")
                    return None
                
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
                # Use a specific port to avoid conflicts
                creds = flow.run_local_server(port=8080)
            
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        return creds

    def upload_short(self, video_path: str, content: Dict) -> bool:
        """Uploads a video to YouTube as a Short."""
        if not YOUTUBE_AVAILABLE:
            print("❌ YouTube libraries not available. Please install them.")
            return False

        print("🚀 Attempting YouTube Shorts upload...")
        
        try:
            credentials = self._get_credentials()
            if not credentials:
                print("❌ Could not get YouTube credentials. Skipping upload.")
                return False

            youtube = build('youtube', 'v3', credentials=credentials)

            # To be a Short, the title or description must include #Shorts
            # and the video must be < 60 seconds and have a vertical aspect ratio.
            # Our videos already meet the duration/aspect ratio requirements.
            title = content['title']
            description = f"{content['story'][:200]}...\n\n{content['hashtags']} #viral #viralvideo #shorts #Shorts"
            
            request_body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': content['hashtags'].replace('#', '').split(),
                    'categoryId': '24'  # Entertainment
                },
                'status': {
                    'privacyStatus': 'public',  # or 'private', 'unlisted'
                    'selfDeclaredMadeForKids': False,
                }
            }

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

            request = youtube.videos().insert(
                part=",".join(request_body.keys()),
                body=request_body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Uploading... {int(status.progress() * 100)}%")
            
            print(f"✅ YouTube video uploaded! Video ID: {response.get('id')}")
            return True

        except Exception as e:
            print(f"❌ YouTube upload failed: {e}")
            # If token is invalid, delete it to force re-auth next time
            if 'invalid_grant' in str(e).lower() and os.path.exists(self.token_file):
                print("🗑️ Deleting invalid YouTube token file.")
                os.remove(self.token_file)
            return False

class MainApp:
    """Orchestrates the entire content creation workflow."""
    def __init__(self):
        self.config = self._load_config()
        if not self.config:
            raise Exception("Configuration file 'config.json' not found or invalid.")
        
        self.content_generator = ContentGenerator(self.config)
        
        # Use FFmpeg processor (required)
        if FFMPEG_PYTHON_AVAILABLE:
            print("🚀 Using FFmpeg for ultra-fast video processing!")
            self.video_processor = FFmpegVideoProcessor(self.config)
            self.use_ffmpeg = True
        else:
            print("❌ FFmpeg not available. Please install ffmpeg-python.")
            raise Exception("FFmpeg is required for video processing.")
            
        self.uploader = InstagramUploader(self.config)
        self.youtube_uploader = YouTubeUploader()
        
        # Unified history tracking file
        self.used_content_file = "used_content.json"

    def _load_config(self) -> Dict:
        """Loads the main configuration file."""
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
    
    def _load_used_content(self) -> Dict:
        """Loads the unified used content tracking data."""
        try:
            if os.path.exists(self.used_content_file):
                with open(self.used_content_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load {self.used_content_file}: {e}")
        
        # Return default structure
        return {
            "videos": [],
            "music": [],
            "reddit_posts": []
        }
    
    def _save_used_content(self, used_content: Dict):
        """Saves the unified used content tracking data."""
        try:
            with open(self.used_content_file, 'w') as f:
                json.dump(used_content, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save to {self.used_content_file}: {e}")
    
    def _mark_as_used(self, category: str, item: str):
        """Marks an item as used in a specific category."""
        used_content = self._load_used_content()
        if category in used_content and item not in used_content[category]:
            used_content[category].append(item)
            self._save_used_content(used_content)
            print(f"✅ Marked as used ({category}): {item}")

    def run(self):
        """Main execution workflow."""
        print("🚀 === STARTING CONTENT CREATOR BOT === 🚀")
        
        # Show tracking status
        instagram_config = self.config.get("instagram", {})
        auto_upload_enabled = instagram_config.get("auto_upload", True)
        
        if auto_upload_enabled:
            used_content = self._load_used_content()
            print(f"\n🔄 Repeat Prevention: ENABLED")
            print(f"   📹 Used videos: {len(used_content['videos'])}")
            print(f"   📝 Used Reddit posts: {len(used_content['reddit_posts'])}")
            print(f"   🎵 Used music: {len(used_content['music'])}")
        else:
            print(f"\n🔄 Repeat Prevention: DISABLED (auto-upload is off)")
        
        # Choose content type
        print("\n📝 Content Types:")
        print("1. 📖 Story/Educational (AI generated)")
        print("2. 🤯 Surprising Facts (like Coca-Cola secrets)")
        print("3. 🌐 Reddit Stories (real stories from Reddit)")
        print("4. ❓ Ask Reddit (questions with top comments)")
        print("5. 🤖 AI-Recommended Reddit Story (Gemini finds viral post)")
        print("6. 🤖 AI-Recommended Ask Reddit (Gemini finds viral question)")
        
        content_choice = input("\nChoose content type (1-6, or press Enter for 1): ").strip()
        
        topic = input("Enter a topic (or press Enter for random): ").strip()
        
        # Choose subtitle style
        print("\n📝 Subtitle Styles:")
        print("1. Single word (one word at a time)")
        print("2. Three words with highlight (grouped with shifting highlight)")
        subtitle_choice = input("Choose subtitle style (1, 2, or press Enter for 2): ").strip()
        subtitle_style = "single_word" if subtitle_choice == "1" else "three_words_highlight"
        
        # Choose card style and animation for Reddit content
        card_style = "white"  # default
        card_animation = "slide"  # default
        if content_choice in ["3", "4", "5", "6"]:  # Reddit content
            print("\n🎨 Reddit Card Style:")
            print("1. White background (light mode)")
            print("2. Black background (dark mode)")
            card_choice = input("Choose card style (1, 2, or press Enter for 1): ").strip()
            card_style = "black" if card_choice == "2" else "white"
            
            print("\n🎬 Reddit Card Animation:")
            print("1. Slide-in from bottom (with wobble effect)")
            print("2. Zoom-in from center (smooth scale-up)")
            animation_choice = input("Choose animation (1, 2, or press Enter for 1): ").strip()
            card_animation = "zoom" if animation_choice == "2" else "slide"
        
        # Check if auto-upload is enabled for tracking purposes
        instagram_config = self.config.get("instagram", {})
        auto_upload_enabled = instagram_config.get("auto_upload", True)
        
        # 1. Generate Content
        if content_choice == "6":
            # AI-recommended Ask Reddit post
            print("🤖 Using Gemini AI to find a viral Ask Reddit post...")
            if auto_upload_enabled:
                used_content = self._load_used_content()
                reddit_scraper = RedditScraper(used_posts_tracker=used_content['reddit_posts'])
            else:
                reddit_scraper = RedditScraper()
            content = reddit_scraper.get_ai_recommended_reddit_post(content_type="ask")
            print(f"📌 Source: {content.get('source', 'Reddit')} - AI recommended!")
        elif content_choice == "5":
            # AI-recommended Reddit story
            print("🤖 Using Gemini AI to find a viral Reddit story...")
            if auto_upload_enabled:
                used_content = self._load_used_content()
                reddit_scraper = RedditScraper(used_posts_tracker=used_content['reddit_posts'])
            else:
                reddit_scraper = RedditScraper()
            content = reddit_scraper.get_ai_recommended_reddit_post(content_type="story")
            print(f"📌 Source: {content.get('source', 'Reddit')} - AI recommended!")
        elif content_choice == "4":
            # Ask Reddit with top comments
            ask_subreddits = self.config.get("ask_subreddits", [
                'AskReddit', 'AskMen', 'AskWomen', 'TooAfraidToAsk', 'NoStupidQuestions', 'AskReddit','AskReddit','AskReddit','AskReddit',
            ])
            if auto_upload_enabled:
                used_content = self._load_used_content()
                reddit_scraper = RedditScraper(used_posts_tracker=used_content['reddit_posts'])
                content = reddit_scraper.get_ask_post_with_comments(ask_subreddits, avoid_repeats=True)
            else:
                reddit_scraper = RedditScraper()
                content = reddit_scraper.get_ask_post_with_comments(ask_subreddits, avoid_repeats=False)
            print(f"📌 Source: {content.get('source', 'Reddit')} - {content['reddit_info'].get('num_comments', 0)} top comments")
        elif content_choice == "3":
            # Reddit scraping with repeat avoidance if auto-upload is on
            if auto_upload_enabled:
                used_content = self._load_used_content()
                reddit_scraper = RedditScraper(used_posts_tracker=used_content['reddit_posts'])
                content = reddit_scraper.get_reddit_story(topic, avoid_repeats=True)
            else:
                reddit_scraper = RedditScraper()
                content = reddit_scraper.get_reddit_story(topic, avoid_repeats=False)
            print(f"📌 Source: {content.get('source', 'Reddit')}")
        elif content_choice == "2":
            # Facts content
            content = self.content_generator.generate_content(topic, "facts")
        else:
            # Default story content
            content = self.content_generator.generate_content(topic, "story")
        if not content:
            print("❌ Failed to generate content. Exiting.")
            return
        print(f"\n📄 Title: {content['title']}\n📝 Story: {content['story'][:70]}...\n🏷️ Hashtags: {content['hashtags']}")

        # 2. Create Voiceover
        # If Reddit content, prepend the title so TTS announces it
        is_reddit = bool(content.get('reddit_info') or str(content.get('source','')).lower().startswith('r/'))
        tts_text = f"{content['title']}. {content['story']}" if is_reddit else content['story']
        
        # Detect narrator gender from the story content
        detected_gender = self.video_processor._detect_narrator_gender(
            text=content['story'], 
            title=content['title']
        )
        
        # Create voiceover with appropriate gender voice
        audio_path = self.video_processor.create_voiceover(tts_text, gender=detected_gender)
        if not audio_path:
            print("❌ Failed to create voiceover. Exiting.")
            return
        
        # Add TTS engine info to content
        content['tts_engine'] = self.video_processor.last_tts_engine

        # 3. Get Background Video
        bg_path = self._get_random_background_video()
        if not bg_path:
            print("❌ No background videos found. Exiting.")
            return
        
        # Store the background video filename for tracking after upload
        bg_video_name = os.path.basename(bg_path)
        
        # 3.5. Get Background Music
        bg_music_path = self._get_random_background_music()
        bg_music_name = os.path.basename(bg_music_path) if bg_music_path else None

        # 4. Create Final Video with user-selected styles
        final_video_path = self.video_processor.create_video_ffmpeg(
            content, audio_path, bg_path, bg_music_path, 
            subtitle_style=subtitle_style, 
            card_style=card_style,
            card_animation=card_animation
        )
        
        # Clean up intermediate audio file
        if os.path.exists(audio_path):
            os.remove(audio_path)

        if not final_video_path:
            print("❌ Failed to create final video. Exiting.")
            return

        # 5. Upload to Instagram (with better error handling)
        instagram_config = self.config.get("instagram", {})
        upload_successful = False
        if instagram_config.get("auto_upload", True):  # Allow disabling auto-upload
            thumbnail_path = FFmpegVideoProcessor(self.config)._extract_thumbnail(video_path=final_video_path, timestamp=4.0)
            upload_successful = self.uploader.upload(final_video_path, thumbnail_path, content)
            if not upload_successful:
                print("⚠️ Auto-upload failed due to Instagram API issues.")
                print("💡 Consider setting 'auto_upload': false in config to skip auto-upload.")
            else:
                # Mark content as used only if upload was successful
                if auto_upload_enabled:
                    # Save used background video
                    self._mark_as_used('videos', bg_video_name)
                    
                    # Save used background music
                    if bg_music_name:
                        self._mark_as_used('music', bg_music_name)
                    
                    # Save used Reddit post ID if applicable
                    if content.get('reddit_info') and content['reddit_info'].get('post_id'):
                        post_id = content['reddit_info']['post_id']
                        self._mark_as_used('reddit_posts', post_id)
        else:
            print("ℹ️ Auto-upload disabled in config.")

        # 6. Upload to YouTube
        youtube_config = self.config.get("youtube", {})
        if youtube_config.get("auto_upload", False): # Default to False
            self.youtube_uploader.upload_short(final_video_path, content)

        # 7. Open folder for manual uploads (if enabled)
        upload_settings = self.config.get("upload_settings", {})
        if upload_settings.get("enable_manual_upload", True):
            self._open_video_folder(final_video_path, content)

        print("\n🎉 === WORKFLOW COMPLETE === 🎉")

    def _get_random_background_video(self) -> str:
        """Selects a random video from the background videos folder, avoiding recent repeats if auto-upload is on."""
        bg_folder = self.config.get("video_settings", {}).get("background_video_path", "background_videos")
        if not os.path.exists(bg_folder):
            print(f"❌ Background video folder not found: {bg_folder}")
            return None
        
        videos = [f for f in os.listdir(bg_folder) if f.lower().endswith(('.mp4', '.mov', '.avi'))]
        if not videos:
            print(f"❌ No videos found in {bg_folder}")
            return None
        
        print(f"🎬 Found {len(videos)} background videos: {', '.join(videos)}")
        
        # Check if auto-upload is enabled
        instagram_config = self.config.get("instagram", {})
        auto_upload_enabled = instagram_config.get("auto_upload", True)
        
        if auto_upload_enabled:
            # Load used videos
            used_content = self._load_used_content()
            used_videos = used_content['videos']
            
            # Find unused videos
            unused_videos = [v for v in videos if v not in used_videos]
            
            # If all videos have been used, reset the list
            if not unused_videos:
                print("🔄 All videos used! Resetting video history...")
                used_content['videos'] = []
                self._save_used_content(used_content)
                unused_videos = videos
            
            print(f"📊 Video stats: {len(unused_videos)} unused, {len(used_videos)} used")
            selected_video_name = random.choice(unused_videos)
        else:
            # Auto-upload disabled, use pure random selection
            print("ℹ️ Auto-upload disabled - using random selection (repeats allowed)")
            selected_video_name = random.choice(videos)
        
        selected_video = os.path.join(bg_folder, selected_video_name)
        print(f"📹 Randomly selected: {selected_video_name}")
        return selected_video
    
    def _get_random_background_music(self) -> str:
        """Selects a random music file from the background music folder, avoiding recent repeats if auto-upload is on."""
        music_folder = self.config.get("video_settings", {}).get("background_music_path", "background_music")
        if not os.path.exists(music_folder):
            print(f"⚠️ Background music folder not found: {music_folder}")
            return None
        
        music_files = [f for f in os.listdir(music_folder) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.ogg'))]
        if not music_files:
            print(f"⚠️ No music files found in {music_folder}")
            return None
        
        print(f"🎵 Found {len(music_files)} background music files: {', '.join(music_files)}")
        
        # Check if auto-upload is enabled
        instagram_config = self.config.get("instagram", {})
        auto_upload_enabled = instagram_config.get("auto_upload", True)
        
        if auto_upload_enabled:
            # Load used music
            used_content = self._load_used_content()
            used_music = used_content['music']
            
            # Find unused music
            unused_music = [m for m in music_files if m not in used_music]
            
            # If all music has been used, reset the list
            if not unused_music:
                print("🔄 All music used! Resetting music history...")
                used_content['music'] = []
                self._save_used_content(used_content)
                unused_music = music_files
            
            print(f"📊 Music stats: {len(unused_music)} unused, {len(used_music)} used")
            selected_music_name = random.choice(unused_music)
        else:
            # Auto-upload disabled, use pure random selection
            print("ℹ️ Auto-upload disabled - using random selection (repeats allowed)")
            selected_music_name = random.choice(music_files)
        
        selected_music = os.path.join(music_folder, selected_music_name)
        print(f"🎶 Randomly selected: {selected_music_name}")
        return selected_music

    def _open_video_folder(self, video_path: str, content: Dict):
        """Opens the output folder and provides info for manual uploads."""
        upload_settings = self.config.get("upload_settings", {})
        
        print("\n🎯 --- MANUAL UPLOAD --- 🎯")
        try:
            abs_path = os.path.abspath(video_path)
            
            # Copy to clipboard if enabled
            if upload_settings.get("copy_path_to_clipboard", True) and pyperclip:
                pyperclip.copy(abs_path)
                print("📋 Video path copied to clipboard.")
            
            # Open folder if enabled
            if upload_settings.get("open_folder_after_creation", True):
                if os.name == 'nt': # Windows
                    subprocess.run(f'explorer /select,"{abs_path}"', shell=True)
                elif os.name == 'posix': # macOS/Linux
                    subprocess.run(['open', '-R', abs_path])
                print("✅ Output folder opened.")
            else:
                print("📁 Folder opening disabled in config.")
            
            print(f"📝 Title: {content['title']}")
            print(f"🏷️ Content Hashtags: {content['hashtags']}")
            tts_name = content.get('tts_engine', 'Edge-TTS')
            print(f"🎙️ Voice Credit: {tts_name}")
            print(f"\n💡 Suggested caption for Instagram Reels:\n{content['title']}\n\n{content['hashtags']} #viral #fy #reels\n\n🎙️ Voice: {tts_name}")
            print(f"\n💡 Suggested caption for YouTube Shorts:\n{content['title']}\n\n{content['hashtags']} #viral #fy #shorts\n\n🎙️ Voice: {tts_name}")

        except Exception as e:
            print(f"❌ Could not open folder: {e}")
            print(f"📁 Video is at: {os.path.abspath(video_path)}")

if __name__ == "__main__":
    try:
        app = MainApp()
        app.run()
    except Exception as e:
        print(f"\n🚨 An unexpected error occurred: {e}")