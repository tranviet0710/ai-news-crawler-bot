# AI-NEWS-CRAWLER
Với tech stack **Python FastAPI, Supabase, OpenAI và GitHub Actions**, hệ thống sẽ hoạt động theo luồng: GitHub Actions làm nhiệm vụ Cronjob (gọi API mỗi giờ) -> FastAPI tiếp nhận request -> Crawl RSS -> OpenAI lọc & tóm tắt -> Lưu Supabase -> Bắn Telegram.

Dưới đây là kế hoạch triển khai từng bước:

### 1. Kiến trúc hệ thống & Danh sách Nguồn tin

Để đảm bảo lấy từ các nguồn "uy tín nhất" và không bị block, chúng ta sẽ ưu tiên sử dụng **RSS Feeds** và **Official APIs**.

* **Nguồn tin AI cốt lõi (RSS):**
* OpenAI Blog: `https://openai.com/blog/rss.xml`
* Google AI Blog: `https://blog.google/technology/ai/rss/`
* Anthropic News: (Sử dụng RSS hub hoặc crawl nhẹ từ trang news của họ).
* Hacker News (Tag: AI/ML): Gọi API trực tiếp lấy top stories.
* TechCrunch (AI Section): `https://techcrunch.com/category/artificial-intelligence/feed/`
* Hugging Face Blog: `https://huggingface.co/blog/feed.xml`



### 2. Cấu trúc thư mục dự án (Project Structure)

Khởi tạo project chuẩn với cấu trúc sau để dễ scale và maintain:

```text
ai-news-service/
├── app/
│   ├── __init__.py
│   ├── main.py                # Điểm nạp của FastAPI
│   ├── core/
│   │   ├── config.py          # Quản lý Environment Variables (pydantic BaseSettings)
│   ├── services/
│   │   ├── crawler.py         # Logic cào dữ liệu (feedparser, requests)
│   │   ├── openai_service.py  # Giao tiếp với OpenAI API (Filter & Tóm tắt)
│   │   ├── supabase_client.py # Giao tiếp với database
│   │   └── telegram_bot.py    # Logic bắn tin nhắn Telegram
│   ├── api/
│   │   └── endpoints.py       # API Routes (ví dụ: POST /api/crawl)
├── .github/
│   └── workflows/
│       └── cronjob.yml        # Cấu hình GitHub Actions
├── requirements.txt           # fastapi, uvicorn, openai, supabase, feedparser, requests...
├── .env.example               # Template chứa các biến môi trường
└── README.md

```

### 3. Chi tiết triển khai (Implementation Phases)

#### Phase 1: Khởi tạo và Cấu hình Database (Supabase)

1. Tạo project trên Supabase.
2. Tạo table `processed_news`:
* `id` (uuid, primary key)
* `url` (text, unique) - Dùng để check trùng lặp.
* `title` (text)
* `published_at` (timestamp)
* `created_at` (timestamp, default `now()`)


3. Tạo file `.env` (không commit lên Git) gồm các biến:
* `OPENAI_API_KEY=`
* `TELEGRAM_BOT_TOKEN=`
* `TELEGRAM_CHAT_ID=`
* `SUPABASE_URL=`
* `SUPABASE_KEY=`



#### Phase 2: Phát triển các Service Modules (Python)

* **`crawler.py`**: Dùng thư viện `feedparser` để đọc RSS feeds. Lấy ra danh sách các object (title, link, description, pubDate) trong vòng 1-2 giờ qua.
* **`supabase_client.py`**: Khởi tạo client. Viết hàm `check_if_exists(url)` và `save_news(url, title)`.
* **`openai_service.py`**:
* Đầu vào: Tiêu đề + Nội dung tóm tắt từ RSS.
* System Prompt: *"Bạn là một chuyên gia AI. Hãy đọc tin tức sau. Nếu nó nói về việc ra mắt model mới, AI agents, hoặc cập nhật quan trọng về AI trong lập trình (OpenAI, Anthropic, Google...), hãy trả về 1 bản tóm tắt ngắn gọn bằng tiếng Việt (tối đa 3 dòng). Nếu không liên quan hoặc là tin rác, trả về chuỗi 'SKIP'."*


* **`telegram_bot.py`**: Dùng `requests` gọi đến `https://api.telegram.org/bot<TOKEN>/sendMessage`. Format tin nhắn bằng HTML hoặc MarkdownV2 cho đẹp (in đậm tiêu đề, chèn link hyperlink).

#### Phase 3: Tích hợp FastAPI

* Trong `main.py`, khởi tạo app FastAPI.
* Tạo một endpoint bảo mật: `POST /api/v1/trigger-crawl`.
* *Security check:* Yêu cầu một header `Authorization: Bearer <SECRET_CRON_KEY>` để tránh việc người lạ gọi API của bạn liên tục.
* *Logic:* Gọi lần lượt Crawler -> Check Supabase -> Bắn qua OpenAI -> Bắn Telegram -> Lưu Supabase.



#### Phase 4: Deploy FastAPI

* Để FastAPI luôn chạy và hứng request từ GitHub Actions, bạn có thể deploy miễn phí lên **Render**, **Koyeb** hoặc **Vercel** (FastAPI chạy rất mượt trên Vercel dạng serverless function).
* Cập nhật các biến môi trường (Env Vars) lên platform bạn chọn deploy.

#### Phase 5: Tự động hóa với GitHub Actions

* Tạo file `.github/workflows/cronjob.yml`.
* Cấu hình trigger chạy mỗi giờ và gọi curl đến endpoint FastAPI đã deploy:

```yaml
name: AI News Crawler Cron

on:
  schedule:
    - cron: '0 * * * *' # Chạy vào phút 0 mỗi giờ
  workflow_dispatch: # Cho phép trigger bằng tay từ giao diện Github

jobs:
  trigger-api:
    runs-on: ubuntu-latest
    steps:
      - name: Call FastAPI Endpoint
        env:
          CRON_SECRET: ${{ secrets.CRON_SECRET }} # Set trong Github Secrets
          API_URL: "https://your-fastapi-domain.com/api/v1/trigger-crawl"
        run: |
          curl -X POST "$API_URL" \
          -H "Authorization: Bearer $CRON_SECRET" \
          -H "Content-Type: application/json"

```

### 4. Luồng xử lý dữ liệu (Data Pipeline)

1. **GitHub Actions** gõ cửa **FastAPI** đúng giờ.
2. **FastAPI** đọc RSS từ 5-10 nguồn uy tín.
3. Lọc bỏ các URL đã có trong **Supabase**.
4. Các URL mới được đưa cho **OpenAI** đọc. Tin nào ra kết quả `SKIP` thì bỏ qua.
5. Tin nào OpenAI tóm tắt thành công -> Format đẹp -> Gửi **Telegram**.
6. Lưu URL vừa gửi vào **Supabase** để giờ sau không gửi lại.

Bạn muốn mình viết chi tiết mã nguồn (source code) cho phần module nào trước? Ví dụ: file cấu hình kết nối Supabase, logic lọc bằng thư viện feedparser, hay phần prompt cho OpenAI?