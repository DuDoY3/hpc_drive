# HPC Drive - Docker Deployment Guide

## 🚀 Quick Start

### Chạy dự án lần đầu hoặc sau khi pull code mới:

```bash
cd /home/dudo/Code_Ngoai/hpc_drive

# Build và start containers
docker compose up -d --build
```

**Đó là tất cả!** 🎉

Migration sẽ tự động chạy khi container khởi động.

---

## 📋 Workflow chi tiết

### 1. Khi code KHÔNG thay đổi database schema

```bash
# Chỉ cần restart service
docker compose restart

# Hoặc rebuild nếu sửa logic code
docker compose up -d --build
```

✅ **Không cần chạy lệnh migration thủ công**

---

### 2. Khi code CÓ thay đổi database schema

**VD**: Bạn thêm field mới trong `models.py`

#### Trên máy dev (local):

```bash
# 1. Tạo migration file
alembic revision --autogenerate -m "Add new field"

# 2. Test migration local trước
alembic upgrade head

# 3. Commit cả code + migration file
git add .
git commit -m "Add new feature with DB migration"
git push
```

#### Trên server/production:

```bash
# Pull code mới
git pull

# Build lại container (migration tự chạy trong entrypoint)
docker compose up -d --build
```

✅ **Migration tự động chạy khi container start**

---

## 🔍 Kiểm tra trạng thái

### Xem logs migration:

```bash
docker compose logs hpc_drive | grep migration
```

Bạn sẽ thấy:
```
📦 Running database migrations...
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
✅ Migrations completed!
```

### Xem database schema hiện tại:

```bash
# Vào container
docker exec -it hpc_drive_service bash

# Mở SQLite
sqlite3 /app/data/drive.db

# Xem bảng
.tables

# Xem cấu trúc bảng
.schema drive_items

# Thoát
.exit
```

### Kiểm tra Alembic version:

```bash
docker exec -it hpc_drive_service alembic current
```

---

## 🛠️ Các lệnh hữu ích

### Chạy migration thủ công (nếu cần):

```bash
docker exec -it hpc_drive_service alembic upgrade head
```

### Rollback migration:

```bash
# Rollback 1 version
docker exec -it hpc_drive_service alembic downgrade -1

# Rollback về version cụ thể
docker exec -it hpc_drive_service alembic downgrade abc123
```

### Xem lịch sử migration:

```bash
docker exec -it hpc_drive_service alembic history
```

---

## 📁 Cấu trúc thư mục quan trọng

```
hpc_drive/
├── Dockerfile                    # Config Docker image
├── docker-compose.yml            # Orchestration config
├── docker-entrypoint.sh          # 🔥 Auto-run migrations
├── alembic.ini                   # Alembic config
├── alembic/
│   ├── env.py                    # Alembic environment
│   └── versions/                 # Migration files
│       └── xxx_add_folder_type.py
├── src/hpc_drive/
│   └── models.py                 # Database models
└── requirements.txt
```

---

## ⚠️ Lưu ý quan trọng

### 1. Data persistence

Database được lưu trong Docker volume `drive_data`:

```bash
# Xem volumes
docker volume ls

# Backup database
docker cp hpc_drive_service:/app/data/drive.db ./backup_$(date +%Y%m%d).db
```

### 2. Khi xóa container

```bash
# Xóa container nhưng GIỮ data
docker compose down

# Xóa container VÀ data (NGUY HIỂM!)
docker compose down -v
```

### 3. Production deployment

Đối với production, nên:

1. **Backup database trước khi deploy**:
   ```bash
   docker exec hpc_drive_service sqlite3 /app/data/drive.db ".backup '/app/data/backup.db'"
   ```

2. **Test migration trên staging trước**

3. **Kiểm tra logs sau deploy**:
   ```bash
   docker compose logs -f hpc_drive
   ```

---

## 🐛 Troubleshooting

### Migration failed khi start container

**Triệu chứng**: Container tự động tắt sau khi start

**Giải pháp**:
```bash
# 1. Xem logs lỗi
docker compose logs hpc_drive

# 2. Vào container debug (nếu rebuild với --no-cache)
docker compose run --rm hpc_drive bash

# 3. Chạy migration thủ công để xem lỗi chi tiết
alembic upgrade head
```

### Database locked error

**Nguyên nhân**: Nhiều process cùng truy cập SQLite

**Giải pháp**:
```bash
# Stop tất cả containers đang dùng database
docker compose down

# Start lại
docker compose up -d
```

---

## 📞 Tóm tắt workflow hàng ngày

| Tình huống | Lệnh cần chạy |
|------------|---------------|
| Start dự án lần đầu | `docker compose up -d --build` |
| Restart sau khi sửa code | `docker compose up -d --build` |
| Pull code mới từ git | `git pull && docker compose up -d --build` |
| Thêm migration mới | `alembic revision --autogenerate -m "..."` |
| Xem logs | `docker compose logs -f hpc_drive` |
| Stop service | `docker compose down` |

**👉 TL;DR: Chỉ cần `docker compose up -d --build`, migration tự động chạy!**
