#!/bin/bash
TOKEN=$(curl -s -X POST -H "Content-Type: application/json" -d '{"username": "gv_gv001", "password": "123456"}' http://localhost:8082/api/v1/login | grep -o '"token":"[^"]*' | grep -o '[^"]*$')
echo "Token: $TOKEN"
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:7777/api/v1/class-storage/auto-generate/1
