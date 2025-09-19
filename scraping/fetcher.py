# 📁 app/scraping/fetcher.py

from fastapi import HTTPException
import feedparser
from bs4 import BeautifulSoup
import json, os, random
from typing import List, Dict, Any
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from fastapi.encoders import jsonable_encoder
from bson import ObjectId

# MongoDB connection with error handling
try:
    client = MongoClient("mongodb+srv://23aiml062_db_user:Wv7GpOzvMuY3y1M2@articles.7hfshvh.mongodb.net/ArticlesDB?retryWrites=true&w=majority&appName=Articles", serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    db = client["news"]
    collection = db["articles"]
    mongodb_available = True
    print("✅ MongoDB connected successfully")
except (ServerSelectionTimeoutError, ConnectionFailure) as e:
    print("⚠️ MongoDB not available, running without database storage from fetcher")
    mongodb_available = False
    client = None
    db = None
    collection = None

# Define your RSS sources
RSS_FEEDS = {
    "ANI": "https://www.aninews.in/rss/national-news.xml",
    "NDTV": "http://feeds.feedburner.com/ndtvnews-top-stories",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "Hindustan Times": "https://www.hindustantimes.com/rss/topnews/rssfeed.xml",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "India Today": "https://www.indiatoday.in/rss/home",
    "News18": "https://www.news18.com/rss/world.xml",
    "DNA India": "https://www.dnaindia.com/feeds/india.xml",
    "Firstpost": "https://www.firstpost.com/rss/india.xml",
    "Business Standard": "https://www.business-standard.com/rss/home_page_top_stories.rss",
    "Outlook India": "https://www.outlookindia.com/rss/main/magazine",
    "Free Press Journal": "https://www.freepressjournal.in/stories.rss",
    "Deccan Chronicle": "https://www.deccanchronicle.com/rss_feed/",
    "Moneycontrol": "http://www.moneycontrol.com/rss/latestnews.xml"
}

# Function to strip HTML tags from RSS summary
def clean_summary(summary_html):
    soup = BeautifulSoup(summary_html, "html.parser")
    return soup.get_text()

def get_news(n: int):
    if n <= 0:
        return {"total": 0, "articles": [], "message": "No articles requested"}
    
    # Get list of available RSS feeds and shuffle them
    rss_sources = list(RSS_FEEDS.items())
    random.shuffle(rss_sources)
    
    all_articles = []
    collected_articles = 0
    processed_sources = set()
    articles_per_source = max(1, n // min(5, len(rss_sources)))  # Distribute across at least 5 sources
    
    # Continue until we've collected enough articles or processed all sources
    while collected_articles < n and len(processed_sources) < len(rss_sources):
        # Get next random source that hasn't been processed yet
        for source_name, url in rss_sources:
            if collected_articles >= n:
                break
                
            if source_name in processed_sources:
                continue
                
            try:
                print(f"Fetching from {source_name}...")
                feed = feedparser.parse(url)
                source_articles = 0
                
                # Process entries from this feed
                for entry in feed.entries:
                    if collected_articles >= n or source_articles >= articles_per_source * 2:  # Allow some flexibility
                        break
                        
                    article_data = {
                        "source": source_name,
                        "title": entry.title.strip(),
                        "summary": clean_summary(entry.summary),
                        "link": entry.link,
                        "published": entry.get("published", "Unknown"),
                        "fetched_at": datetime.utcnow().isoformat()
                    }
                    
                    # Check for duplicates before adding
                    if not any(a['title'].lower() == article_data['title'].lower() for a in all_articles):
                        all_articles.append(article_data)
                        collected_articles += 1
                        source_articles += 1
                
                processed_sources.add(source_name)
                print(f"  - Found {source_articles} new articles from {source_name}")
                
                # If we've processed enough sources to potentially get the requested articles, break early
                if len(processed_sources) >= min(5, len(rss_sources)) and collected_articles >= n:
                    break
                    
            except Exception as e:
                print(f"Error fetching from {source_name}: {str(e)}")
                processed_sources.add(source_name)
                continue
    
    # Save to MongoDB if available
    saved_count = 0
    if mongodb_available and collection is not None and all_articles:
        try:
            # Prepare bulk operations for upsert
            operations = []
            for article in all_articles:
                operations.append(
                    UpdateOne(
                        {"title": article["title"], "source": article["source"]},
                        {"$setOnInsert": article},
                        upsert=True
                    )
                )
            
            if operations:
                result = collection.bulk_write(operations, ordered=False)
                saved_count = result.upserted_count + result.modified_count
                print(f"✅ Saved {saved_count} articles to MongoDB")
                
        except Exception as e:
            print(f"⚠️ Failed to save to MongoDB: {e}")
    
    # Prepare response
    articles_for_return = jsonable_encoder(
        all_articles,
        custom_encoder={ObjectId: str}
    )
    
    return {
        "total": len(articles_for_return),
        "articles": articles_for_return,
        "message": f"Fetched {len(articles_for_return)} articles from {len(processed_sources)} sources"
    }
