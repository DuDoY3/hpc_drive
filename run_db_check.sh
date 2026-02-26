#!/bin/bash
docker cp /home/dudo/Code_Ngoai/hpc_drive/check_db2.py hpc_drive_service:/app/
docker exec hpc_drive_service python /app/check_db2.py
docker cp hpc_drive_service:/app/db_output.txt /home/dudo/Code_Ngoai/hpc_drive/db_output.txt
