# Thiết Kế Việt Hóa Nội Dung Bot Telegram

Ngày: 2026-03-21

## Mục tiêu

Việt hóa toàn bộ chuỗi hiển thị cho người dùng trong bot Telegram sang tiếng Việt có dấu, đồng thời giữ nguyên command, endpoint, schema dữ liệu và logic xử lý hiện tại.

## Phạm vi

- Chỉ cập nhật nội dung bot Telegram mà người dùng nhìn thấy
- Không chỉnh `README.md`, spec, plan hay tài liệu khác
- Không đổi `/start`, `/stop`, `/status`, `/help`
- Không đổi luồng subscribe, webhook, pipeline, Supabase

## Cách tiếp cận được chọn

Việt hóa toàn bộ chuỗi hiển thị trong lớp `TelegramBot` và cập nhật test tương ứng.

### Lý do

- Giữ thay đổi nhỏ, rõ ràng, ít rủi ro
- Cải thiện UX ngay cho người dùng cuối
- Không ảnh hưởng tích hợp hiện có

## Thành phần thay đổi

### `app/services/telegram_bot.py`

Cập nhật các chuỗi:

- `Nguồn` thay cho `Nguon`
- `Đọc chi tiết` thay cho `Doc chi tiet`
- tin nhắn chào mừng có dấu
- tin nhắn trợ giúp có dấu
- tin nhắn trạng thái có dấu
- tin nhắn dừng nhận tin có dấu
- tin nhắn yêu cầu nhắn riêng có dấu

### `tests/test_telegram_bot.py`

Cập nhật assertion cho các chuỗi có dấu mới.

### `tests/test_trigger_crawl.py`

Cập nhật stub message và assertion để phản ánh nội dung tiếng Việt có dấu khi webhook trả lời người dùng.

### `app/api/endpoints.py`

Di chuyển hoặc dùng helper cho nội dung phản hồi `/stop` để chuỗi này cũng được Việt hóa có dấu và không còn bị hardcode ngoài service bot.

## Nguyên tắc nội dung

- Ngắn gọn, tự nhiên, dễ hiểu
- Dùng tiếng Việt có dấu đầy đủ
- Giữ các command ở dạng gốc để tương thích với Telegram
- Không thêm tính năng mới hoặc thay đổi giọng điệu quá nhiều

## Hành vi sau thay đổi

- Người dùng gửi `/start` sẽ nhận được lời chào tiếng Việt có dấu
- Người dùng gửi `/help` sẽ nhận được hướng dẫn tiếng Việt có dấu
- Người dùng gửi `/status` sẽ nhận được trạng thái tiếng Việt có dấu
- Người dùng gửi `/stop` sẽ nhận được xác nhận dừng nhận tin bằng tiếng Việt có dấu
- Khi bot gửi bản tin, phần nhãn và liên kết hiển thị bằng tiếng Việt có dấu

## Kiểm thử

- Test unit cho `TelegramBot`
- Test webhook hiện có trong `tests/test_trigger_crawl.py`
- Có test xác nhận phản hồi `/stop` bằng tiếng Việt có dấu
- Không cần thay đổi test pipeline ngoài các assertion nội dung nếu có liên quan

## Tiêu chí hoàn thành

- Không còn chuỗi bot hiển thị không dấu trong phạm vi đã chọn
- Tất cả test liên quan vẫn pass
- Không có thay đổi logic ngoài phần nội dung hiển thị
