# Telegram Bot Vietnamese Copy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Việt hóa toàn bộ chuỗi hiển thị cho người dùng trong bot Telegram sang tiếng Việt có dấu, không đổi logic.

**Architecture:** Chỉ cập nhật các chuỗi hiển thị trong service bot và phản hồi webhook `/stop`, rồi chỉnh lại test tương ứng. Không thay đổi command, endpoint, schema hay pipeline.

**Tech Stack:** Python, FastAPI, pytest

---

## Chunk 1: Việt hóa chuỗi bot và test

### Task 1: Cập nhật chuỗi hiển thị trong bot Telegram

**Files:**
- Modify: `app/services/telegram_bot.py`
- Modify: `app/api/endpoints.py`
- Modify: `tests/test_telegram_bot.py`
- Modify: `tests/test_trigger_crawl.py`

- [ ] **Step 1: Viết test fail cho chuỗi có dấu**

Thêm hoặc cập nhật test để assert các chuỗi sau có dấu:

```python
assert "Nguồn:" in text
assert "Đọc chi tiết" in text
assert bot.build_welcome_message() == "Chào mừng bạn. Gửi /start để đăng ký, /stop để dừng nhận tin, /status để xem trạng thái."
assert bot.build_help_message() == "Lệnh hỗ trợ: /start, /stop, /status, /help"
assert bot.build_private_chat_only_message() == "Hãy nhắn tin riêng cho bot và gửi /start để đăng ký."
```

Với webhook test, thêm assertion cho phản hồi `/stop` có dấu.

- [ ] **Step 2: Chạy test để xác nhận đang fail**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_telegram_bot.py tests/test_trigger_crawl.py -v
```

Expected: FAIL do chuỗi hiện tại chưa có dấu đầy đủ.

- [ ] **Step 3: Viết code tối thiểu để pass**

Cập nhật:

- `Nguon` -> `Nguồn`
- `Doc chi tiet` -> `Đọc chi tiết`
- các câu chào mừng, trợ giúp, trạng thái, nhắn riêng sang tiếng Việt có dấu
- thêm helper như `build_stop_message()` trong `app/services/telegram_bot.py`
- dùng helper đó trong `app/api/endpoints.py` thay vì hardcode chuỗi `/stop`

- [ ] **Step 4: Chạy lại test mục tiêu**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_telegram_bot.py tests/test_trigger_crawl.py -v
```

Expected: PASS.

### Task 2: Chạy hồi quy toàn bộ test liên quan

**Files:**
- Test: `tests/test_telegram_bot.py`
- Test: `tests/test_trigger_crawl.py`
- Test: `tests/test_news_pipeline.py`

- [ ] **Step 1: Chạy nhóm test liên quan**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_telegram_bot.py tests/test_trigger_crawl.py tests/test_news_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 2: Chạy full test suite**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -v
```

Expected: PASS.
