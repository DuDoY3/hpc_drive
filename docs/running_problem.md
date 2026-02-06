# Running Problem

## Behavior
- Run `docker compose up -d`
- Postman: GET `http://0.0.0.0:7777/api/v1/drive/items`
  - **Response**:
    ```json
    {
      "detail": "Could not connect to authentication service"
    }
    ```
- Run `docker compose down`
- Run `uvicorn --app-dir src hpc_drive.main:app --host 0.0.0.0 --port 7777 --reload`
- Postman: GET `http://0.0.0.0:7777/api/v1/drive/items`
  - **Response**:
    ```json
    {
        "parent_id": null,
        "items": [
            {
                "name": "auth_service_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "1cc12080-335f-4ea4-8a39-a0b9c5e71980",
                "owner_id": 2,
                "created_at": "2025-11-03T13:07:52",
                "updated_at": "2025-11-11T07:11:38",
                "is_trashed": false,
                "permission": "SHARED",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 23523,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/f7b25385-e893-42ff-96a4-63a3b8ca7c29/auth_service_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "auth_service_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "130ba4d3-651a-47fa-9809-761cb4c4091d",
                "owner_id": 2,
                "created_at": "2025-11-03T14:17:02",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 23523,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/51f3a5e5-9515-46a8-8d34-4e10345ab62c/auth_service_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "auth_service_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "970e3f80-0bc4-4da9-8a83-5c24b623100d",
                "owner_id": 2,
                "created_at": "2025-11-03T14:21:17",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 23523,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/112f51b0-15e0-49fc-9721-c80999904cee/auth_service_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "auth_service_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "dd042208-b0b4-43d0-9d03-b0c44c7a58a6",
                "owner_id": 2,
                "created_at": "2025-11-03T14:31:00",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 23523,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/d77878cd-bdfe-4df1-9416-67bfb7735259/auth_service_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "auth_service_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "2caf96fa-2714-4a20-8e3b-3c2b518b5460",
                "owner_id": 2,
                "created_at": "2025-11-03T14:32:12",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 23523,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/e371394e-c16f-412f-be29-116352dd2f01/auth_service_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "drive_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "3c88bc27-42b8-4beb-b6ce-fe00310556f3",
                "owner_id": 2,
                "created_at": "2025-11-03T13:02:57",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 6530,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/f4bac6c5-4262-4e7c-9e32-884ca9de2a49/drive_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "drive_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "56d4d682-ea13-4aa7-b0d7-e3855255b6e7",
                "owner_id": 2,
                "created_at": "2025-11-03T14:10:30",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 6530,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/bee5ae11-f16f-4c52-b341-155e766fed4c/drive_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "drive_api_doc.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "9e4c4a84-6254-48d8-b732-b7db1d834cec",
                "owner_id": 2,
                "created_at": "2025-11-03T14:20:03",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 6530,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/0c49f062-7ec3-48d2-a765-3871428530d7/drive_api_doc.md",
                    "version": 1
                }
            },
            {
                "name": "edge_of_dawn.org",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "21e982e0-7988-45c2-ad38-4ff5dd58c1db",
                "owner_id": 2,
                "created_at": "2025-11-02T11:19:16",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "jane_doe.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "e6d1e176-9763-40e9-a0b5-2c67a0806009",
                "owner_id": 2,
                "created_at": "2025-11-02T10:31:13",
                "updated_at": "2025-11-02T10:54:31.497784",
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "lecturer_student_bugs.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "411cf058-6146-4c39-8e44-279048a81140",
                "owner_id": 2,
                "created_at": "2025-11-03T08:36:24",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 0,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/0adb737c-96d1-4de7-bb35-1f03c4c4e00d/lecturer_student_bugs.md",
                    "version": 1
                }
            },
            {
                "name": "service_info.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "88b80d2c-ce57-4177-b918-8a5dab41650c",
                "owner_id": 2,
                "created_at": "2025-11-02T10:44:46",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 3335,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/115f38ba-5e46-43bf-a2e2-56103bd78260/service_info.md",
                    "version": 1
                }
            },
            {
                "name": "student_account_info_fetch_bug_fix.md",
                "item_type": "FILE",
                "parent_id": null,
                "item_id": "d1ae9a98-e917-4081-8b85-6d293cc9c77a",
                "owner_id": 2,
                "created_at": "2025-11-03T07:59:40",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": {
                    "mime_type": "text/markdown",
                    "size": 8723,
                    "storage_path": "/home/nguyenhieu/backpack/projects/github/stardust-zip/hpc_drive/src/hpc_drive/uploads/2/f90ba8ee-5c29-4e93-8339-6bcf75718a70/student_account_info_fetch_bug_fix.md",
                    "version": 1
                }
            },
            {
                "name": "11-11",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "18072706-4c3b-4df8-8bf7-20d6aa2b5778",
                "owner_id": 2,
                "created_at": "2025-11-11T06:45:03",
                "updated_at": "2025-11-11T06:46:36",
                "is_trashed": false,
                "permission": "SHARED",
                "file_metadata": null
            },
            {
                "name": "My New Folder",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "36ae36d5-2556-4cce-8734-f1dbaf5da265",
                "owner_id": 2,
                "created_at": "2025-11-03T04:09:59",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "My New Folder",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "e61e0431-051f-472a-bfcd-454213f7b1bd",
                "owner_id": 2,
                "created_at": "2025-11-03T04:22:54",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "du do",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "13003839-3517-4bb6-8b21-3be1166ba837",
                "owner_id": 2,
                "created_at": "2025-11-02T12:12:58",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "hello_there",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "26258825-d3e0-4989-90b6-ca14feb57dfe",
                "owner_id": 2,
                "created_at": "2025-11-02T12:43:18",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            },
            {
                "name": "xin chap",
                "item_type": "FOLDER",
                "parent_id": null,
                "item_id": "6bca8858-459b-4353-9e90-ecd961cba27f",
                "owner_id": 2,
                "created_at": "2025-11-03T03:00:09",
                "updated_at": null,
                "is_trashed": false,
                "permission": "PRIVATE",
                "file_metadata": null
            }
        ]
    }
    ```

## Expected Behavior

- Using docker should return the same result as uvicorn


## User service is running (`/home/nguyenhieu/projects/github/others/System-Management`)
### docker-compose.yml
```yaml
services:
    app:
        build:
            context: .
            dockerfile: Dockerfile
        container_name: hpc_app
        restart: unless-stopped
        working_dir: /var/www
        volumes:
            - .:/var/www
        networks:
            - hpc_network

    webserver:
        image: nginx:alpine
        container_name: hpc_web
        restart: unless-stopped
        ports:
            - "8082:80"
        volumes:
            - .:/var/www
            - ./nginx.conf:/etc/nginx/conf.d/default.conf
        depends_on:
            - app
        networks:
            - hpc_network

    db:
        image: mysql:8.0
        container_name: hpc_db
        restart: unless-stopped
        environment:
            MYSQL_ROOT_PASSWORD: root
            MYSQL_DATABASE: system_services
            MYSQL_USER: system_services
            MYSQL_PASSWORD: hpc123
        ports:
            - "3307:3306"
            - "3307:3306"
        volumes:
            - db_data:/var/lib/mysql
        networks:
            - hpc_network

    redis:
        image: redis:alpine
        container_name: hpc_redis
        restart: unless-stopped
        ports:
            - "6380:6379"
        networks:
            - hpc_network

    reverb:
        build:
            context: .
            dockerfile: Dockerfile
        container_name: hpc_reverb
        command: php artisan reverb:start
        working_dir: /var/www
        volumes:
            - .:/var/www
        depends_on:
            - app
            - redis
        ports:
            - "8081:8082"
        networks:
            - hpc_network

    zookeeper:
        image: confluentinc/cp-zookeeper:latest
        container_name: hpc_zookeeper
        restart: unless-stopped
        healthcheck:
          test: ["CMD", "bash", "-c", "echo 'ruok' | nc -w 2 localhost 2181"]
          interval: 10s
          timeout: 5s
          retries: 5
        environment:
            ZOOKEEPER_CLIENT_PORT: 2181
            ZOOKEEPER_TICK_TIME: 2000
        ports:
            - "2181:2181"
        networks:
            - hpc_network

    kafka:
        image: confluentinc/cp-kafka:6.2.10
        container_name: hpc_kafka
        restart: unless-stopped
        depends_on:
          zookeeper:
            condition: service_healthy
        ports:
          - "9092:9092" # Port for external connections
        environment:
          KAFKA_BROKER_ID: 1
          KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
          # --- START OF THE CORRECT CONFIGURATION ---
          KAFKA_LISTENERS: INTERNAL://0.0.0.0:29092,EXTERNAL://0.0.0.0:9092
          KAFKA_ADVERTISED_LISTENERS: INTERNAL://kafka:29092,EXTERNAL://localhost:9092
          KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
          KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
          # --- END OF THE CORRECT CONFIGURATION ---
          KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
          KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
          KAFKA_NUM_PARTITIONS: 3
          KAFKA_DEFAULT_REPLICATION_FACTOR: 1
        networks:
          - hpc_network

    queue:
        build:
            context: .
            dockerfile: Dockerfile
        container_name: hpc_queue
        restart: unless-stopped
        working_dir: /var/www
        volumes:
            - .:/var/www
        command: sh -c "while ! nc -z kafka 29092; do echo 'Waiting for Kafka...'; sleep 1; done; echo 'Kafka is up!'; php artisan queue:work --queue=emails --verbose --tries=3 --timeout=90"
        depends_on:
            - app
            - redis
        networks:
            - hpc_network

    queue_default:
        build:
            context: .
            dockerfile: Dockerfile
        container_name: hpc_queue_default
        restart: unless-stopped
        working_dir: /var/www
        volumes:
            - .:/var/www
        command: sh -c "while ! nc -z kafka 29092; do echo 'Waiting for Kafka...'; sleep 1; done; echo 'Kafka is up!'; php artisan queue:work --verbose --tries=3 --timeout=90"
        depends_on:
            - app
            - redis
        networks:
            - hpc_network

    kafka_consumer:
        build:
            context: .
            dockerfile: Dockerfile
        container_name: hpc_kafka_consumer
        restart: unless-stopped
        working_dir: /var/www
        volumes:
            - .:/var/www
        command: php artisan kafka:consume
        depends_on:
            - app
            - kafka
        networks:
            - hpc_network

networks:
    hpc_network:

volumes:
    db_data:
```

### .env
```env
APP_NAME="System Management"
APP_ENV=local
APP_KEY=base64:mcpsuBdzZrrNWgkeea8LsQGnKPMMFnwRBgPiwI68NXc=
APP_DEBUG=true
APP_URL=http://localhost:8082

LOG_CHANNEL=stack
LOG_DEPRECATIONS_CHANNEL=null
LOG_LEVEL=debug

DB_CONNECTION=mysql
DB_HOST=db
DB_PORT=3306
DB_DATABASE=system_services
DB_USERNAME=system_services
DB_PASSWORD=hpc123

BROADCAST_DRIVER=reverb
CACHE_DRIVER=redis
FILESYSTEM_DISK=local
QUEUE_CONNECTION=redis
SESSION_DRIVER=redis
SESSION_LIFETIME=120
QUEUE_FAILED_DRIVER=database-uuids
CACHE_PREFIX=system_services
SESSION_PREFIX=system_services

MEMCACHED_HOST=127.0.0.1

REDIS_HOST=hpc_redis
REDIS_PASSWORD=null
REDIS_PORT=6379

MAIL_MAILER=smtp
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=dovananh145203@gmail.com
MAIL_PASSWORD=xmcmiigbugedgsyd
MAIL_ENCRYPTION=tls
MAIL_FROM_ADDRESS=dovananh145203@gmail.com
MAIL_FROM_NAME="System Service"


AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
AWS_BUCKET=
AWS_USE_PATH_STYLE_ENDPOINT=false

REVERB_APP_ID=local_app_id
REVERB_APP_KEY=local_app_key
REVERB_APP_SECRET=local_app_secret
REVERB_HOST=localhost
REVERB_PORT=8081
REVERB_SCHEME=http

PUSHER_APP_CLUSTER=mt1

VITE_APP_NAME="${APP_NAME}"

VITE_PUSHER_APP_KEY="${REVERB_APP_KEY}"
VITE_PUSHER_HOST="${REVERB_HOST}"
VITE_PUSHER_PORT="${REVERB_PORT}"
VITE_PUSHER_SCHEME="${REVERB_SCHEME}"

VITE_PUSHER_APP_CLUSTER="${PUSHER_APP_CLUSTER}"

JWT_SECRET=feufiwfiobdsfoiwehoasdfiuafasdhfbsdhjfgfbsdkvjbefheibsdf
JWT_ALGO=HS256
JWT_TTL=3600
JWT_REFRESH_TTL=20160

KAFKA_BROKERS=kafka:29092
```

### temp token (lecturer1)
eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOjIsInVzZXJfdHlwZSI6ImxlY3R1cmVyIiwidXNlcm5hbWUiOiJsZWN0dXJlcjEiLCJpc19hZG1pbiI6ZmFsc2UsImVtYWlsIjoibGVjdHVyZXIxQHN5c3RlbS5jb20iLCJmdWxsX25hbWUiOiJMZWN0dXJlciAxIiwiZGVwYXJ0bWVudF9pZCI6MSwiY2xhc3NfaWQiOm51bGwsImlhdCI6MTc2MzE3MTg2NywiZXhwIjoxNzYzMzg3ODY3fQ.tWfDNGt-XJXd8DxYhgWENoVPfEYsDVZAgem7-gj1VQs
