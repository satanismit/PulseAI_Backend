from fastapi import APIRouter
from scraping.fetcher import get_news 
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

router = APIRouter()

# MongoDB connection with error handling
try:
    client = MongoClient("mongodb+srv://23aiml062_db_user:Wv7GpOzvMuY3y1M2@articles.7hfshvh.mongodb.net/ArticlesDB?retryWrites=true&w=majority&appName=Articles", serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    db = client["news"]
    collection = db["articles"]
    mongodb_available = True
except (ServerSelectionTimeoutError, ConnectionFailure) as e:
    mongodb_available = False
    client = None
    db = None
    collection = None

@router.get("/news/{article}")
def read_news(article: int):
    return get_news(article)

@router.get("/articles")
def get_articles_from_mongodb(limit: int = None):
    """Get articles from MongoDB with optional limit, sorted by published date (newest first)"""
    if not mongodb_available or not collection:
        return {"error": "MongoDB not available", "total": 0, "articles": []}
    
    try:
        # First, ensure we have an index on the published field for better performance
        collection.create_index([("published", -1)])
        
        # Query to get all articles, excluding _id
        # Sort by published date in descending order (newest first)
        # Use a stable sort to maintain consistent ordering
        pipeline = [
            {"$match": {"published": {"$exists": True, "$ne": "Unknown"}}},
            {"$addFields": {
                "published_date": {
                    "$dateFromString": {
                        "dateString": "$published",
                        "onError": "$fetched_at"  # Fallback to fetched_at if published date is invalid
                    }
                }
            }},
            {"$sort": {"published_date": -1}},  # Sort by parsed date
            {"$project": {
                "_id": 0,
                "published_date": 0  # Remove the temporary field from results
            }}
        ]
        
        # Apply limit if specified
        if limit and limit > 0:
            pipeline.append({"$limit": limit})
        
        # Execute the aggregation pipeline
        articles = list(collection.aggregate(pipeline))
        total_articles = collection.count_documents({"published": {"$exists": True, "$ne": "Unknown"}})
        
        # If no articles with valid published dates, fall back to simple sort
        if not articles:
            cursor = collection.find(
                {"published": {"$exists": True}}, 
                {"_id": 0}
            ).sort("published", -1)
            
            if limit and limit > 0:
                cursor = cursor.limit(limit)
                
            articles = list(cursor)
            total_articles = collection.count_documents({"published": {"$exists": True}})
        
        return {
            "total": total_articles,
            "count": len(articles),
            "limit": limit,
            "articles": articles
        }
    except Exception as e:
        return {"error": str(e), "total": 0, "articles": []}




