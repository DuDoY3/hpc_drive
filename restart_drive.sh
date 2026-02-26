#!/bin/bash
docker restart hpc_drive_service
sleep 2
docker logs --tail 50 hpc_drive_service
