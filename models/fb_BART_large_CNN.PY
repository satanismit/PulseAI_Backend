from transformers import pipeline
import os

# Global variable to store the summarizer
summarizer = None

def load_summarizer():
    """Load the BART model lazily when first needed"""
    global summarizer
    if summarizer is None:
        print("🔄 Loading BART model (this may take a few minutes on first run)...")
        
        # Set environment variable to disable symlink warnings
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        
        try:
            summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
            print("✅ BART model loaded successfully!")
        except Exception as e:
            print(f"❌ Failed to load BART model: {e}")
            raise e
    
    return summarizer

def get_custom_summary(text, level="medium"):
    """
    Generate custom summaries based on level
    
    Args:
        text (str): Input text to summarize
        level (str): "low", "medium", or "big" for different summary lengths
    
    Returns:
        dict: Summary result with text and metadata
    """
    
    # Define parameters for different levels
    level_configs = {
        "low": {"max_length": 50, "min_length": 20},      # Very brief
        "medium": {"max_length": 130, "min_length": 50},   # Balanced
        "big": {"max_length": 250, "min_length": 100}      # Detailed
    }
    
    # Get config for the specified level
    config = level_configs.get(level, level_configs["medium"])
    
    try:
        # Load the model if not already loaded
        model = load_summarizer()
        
        # Generate summary with custom parameters
        summary_result = model(
            text, 
            max_length=config["max_length"], 
            min_length=config["min_length"], 
            do_sample=False
        )
        
        return {
            "success": True,
            "summary": summary_result[0]['summary_text'],
            "level": level,
            "original_length": len(text.split()),
            "summary_length": len(summary_result[0]['summary_text'].split()),
            "compression_ratio": round(len(summary_result[0]['summary_text'].split()) / len(text.split()), 2)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "level": level
        }

# Test function (can be removed in production)
def test_summarization():
    """Test function - loads model only when called"""
    article = """
    India successfully launched its first solar observation mission, Aditya-L1, 
    from the Sriharikota space center on Saturday. The spacecraft will study the Sun 
    from a halo orbit around the Lagrange point 1, about 1.5 million km from Earth. 
    This will help scientists better understand solar activities and their impact 
    on space weather, which can affect satellites, communication systems, and power grids on Earth.
    """
    
    for level in ["low", "medium", "big"]:
        print(f"\n=== {level.upper()} SUMMARY ===")
        result = get_custom_summary(article, level)
        if result["success"]:
            print(f"Summary: {result['summary']}")
            print(f"Compression: {result['compression_ratio']}x")
        else:
            print(f"Error: {result['error']}")

# Don't auto-load model on import - only load when actually needed
if __name__ == "__main__":
    test_summarization()
