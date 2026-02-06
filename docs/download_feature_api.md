# 📥 Download Feature API Documentation

This document outlines the API for downloading files from the Drive service, intended for the frontend team's integration.

## Base URL

The base URL for the Drive service API is:

```
http://localhost:8082/api/v1/drive
```

(Note: This is a placeholder. The actual base URL might differ in production environments.)

## Authentication

All download endpoints require a JWT token in the `Authorization` header:

```
Authorization: Bearer {JWT_TOKEN}
```

This token is obtained from the Auth Module's login API.

---

# 1. Download File

Allows users to download a specific file from the Drive service.

**GET** `/items/{itemId}/download`

**Description:**
This endpoint initiates the download of a file identified by its `itemId`. The user must have appropriate permissions (at least `VIEWER` or be the `owner`) for the file to be able to download it.

**Headers:**

```
Authorization: Bearer {JWT_TOKEN}
```

**Path Parameters:**

| Name     | Type   | Description                               |
| -------- | ------ | ----------------------------------------- |
| `itemId` | `string` | **Required**. The unique identifier of the file to be downloaded. |

**Response Success (200 OK):**

The response will be a file stream. The `Content-Disposition` header will typically suggest a filename for the download.

```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="your_file_name.pdf"
Content-Length: [file_size_in_bytes]

[Binary content of the file]
```

**Example Response for a PDF file:**

```
Content-Type: application/pdf
Content-Disposition: attachment; filename="document.pdf"
Content-Length: 123456
```
(Followed by the binary content of `document.pdf`)

**Response Error (4xx/5xx):**

| Status Code | Response Body Example                   | Description                                    |
| ----------- | --------------------------------------- | ---------------------------------------------- |
| `401`       | `{"message": "Unauthorized"}`           | Token missing or invalid/expired.              |
| `403`       | `{"message": "Forbidden", "detail": "User does not have permission to download this file."}` | The authenticated user does not have permission to download the file. |
| `404`       | `{"message": "Not Found", "detail": "File with ID 'abc-123' not found or is a folder."}` | The `itemId` does not correspond to an existing file, or it refers to a folder. |
| `500`       | `{"message": "Internal Server Error", "detail": "Could not retrieve file from storage."}` | An unexpected error occurred on the server, e.g., file not found on the storage backend. |

---

## Notes

1.  **File Permissions**: Ensure the authenticated user has at least `VIEWER` permission or is the `owner` of the file.
2.  **Folder Download**: This endpoint is designed for files. Attempting to download a folder will result in a `404 Not Found` error.
3.  **Error Handling**: The frontend should gracefully handle various HTTP error codes and display appropriate messages to the user.