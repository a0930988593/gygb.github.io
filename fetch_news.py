import feedparser
from jinja2 import Template
import datetime

# 1. 定義您想收錄的國際與台灣財經新聞 RSS 來源
NEWS_SOURCES = {
    "國際總經 (CNBC)": "https://cnbc.com",
    "美股訊息 (Yahoo Finance)": "https://yahoo.com",
    "台股與綜合 (鉅亨網)": "https://cnyes.com",
}

def fetch_all_news():
    all_news = {}
    for category, url in NEWS_SOURCES.items():
        print(f"正在抓取: {category}...")
        feed = feedparser.parse(url)
        # 每個來源只取前 8 則最新新聞
        articles = []
        for entry in feed.entries[:8]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.get("published", entry.get("updated", "未知時間"))
            })
        all_news[category] = articles
    return all_news

def generate_html(news_data):
    # HTML 網頁範本
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>我的私人財經新聞聚合站</title>
        <link href="https://jsdelivr.net" rel="stylesheet">
        <style>
            body { background-color: #f8f9fa; font-family: 'Helvetica Neue', Arial, sans-serif; }
            .card { border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }
            .card-title { color: #0d6efd; font-weight: bold; }
            .update-time { font-size: 0.85rem; color: #6c757d; }
            .news-list-item { border-bottom: 1px solid #edf2f7; padding: 10px 0; }
            .news-list-item:last-child { border-bottom: none; }
            a { text-decoration: none; color: #212529; }
            a:hover { color: #0a58ca; text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container py-4">
            <header class="pb-3 mb-4 border-bottom d-flex justify-content-between align-items-center">
                <span class="fs-4 fw-bold">📈 個人財經新聞監控牆</span>
                <span class="update-time">最後更新時間 (UTC): {{ update_time }}</span>
            </header>

            <div class="row">
                {% for category, articles in news_data.items() %}
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title border-bottom pb-2">{{ category }}</h5>
                            <div class="news-list">
                                {% for article in articles %}
                                <div class="news-list-item">
                                    <a href="{{ article.link }}" target="_blank"><strong>{{ article.title }}</strong></a>
                                    <div class="update-time mt-1">{{ article.published }}</div>
                                </div>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </body>
    </html>
    """
    
    current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    template = Template(html_template)
    rendered_html = template.render(news_data=news_data, update_time=current_time)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print("index.html 產生成功！")

if __name__ == "__main__":
    data = fetch_all_news()
    generate_html(data)
