from app.core.config import Settings


def test_default_rss_sources_include_curated_feeds():
    settings = Settings(_env_file=None)

    assert settings.rss_source_list == [
        "https://openai.com/blog/rss.xml",
        "https://blog.google/technology/ai/rss/",
        "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_anthropic_news.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://huggingface.co/blog/feed.xml",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "https://research.google/blog/rss/",
        "https://engineering.fb.com/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://news.mit.edu/rss/topic/artificial-intelligence2",
        "https://bair.berkeley.edu/blog/feed.xml",
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "https://hacker-news.firebaseio.com/v0/topstories.json",
    ]
