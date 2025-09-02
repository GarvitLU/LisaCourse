# 📚 Curriculum Generation API

A powerful Flask-based API that transforms PDF documents into comprehensive educational curricula with AI-generated images and seamless Lisa app integration.

## ✨ Features

- **📄 PDF Text Extraction**: Robust text extraction from uploaded PDF files using PyPDF2
- **🤖 AI Curriculum Generation**: Intelligent curriculum creation using OpenAI GPT-4o-mini
- **🎨 AI Image Generation**: High-quality educational illustrations using Ideogram API
- **☁️ S3 Image Storage**: Permanent image storage in AWS S3 with automatic upload
- **🎓 Lisa Course Integration**: Direct course and module slide creation in Lisa app
- **🔐 JWT Authentication**: Secure API access with JWT token management
- **📱 Web Interface**: User-friendly HTML interface for PDF upload and preview
- **🔄 Complete Workflow**: End-to-end process from PDF to published course

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- OpenAI API key (for curriculum generation)
- Ideogram API key (for image generation)
- AWS S3 credentials (for image storage)
- Lisa app access (for course creation)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd 28-LisaCourse
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp config.env.example .env
   ```
   
   Edit `.env` and add your API keys:
   ```bash
   OPENAI_API_KEY=your_openai_api_key_here
   IDEOGRAM_API_KEY=your_ideogram_api_key_here
   AWS_ACCESS_KEY_ID=your_aws_access_key_id
   AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
   AWS_REGION=us-east-1
   S3_BUCKET_NAME=your-s3-bucket-name
   LISA_AUTHORIZATION_TOKEN=your_lisa_token_here
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

   Or use the start script:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

The API will be available at `http://localhost:5001`

## 🌐 Web Interface

Visit `http://localhost:5001` to access the web interface where you can:
- Upload PDF files
- Generate curricula with AI
- Preview generated content and images
- View structured course data

## 📡 API Endpoints

### Core Endpoints

#### 1. **Generate Curriculum** (Main Endpoint)
**POST** `/generate-curriculum`

Upload a PDF to generate a complete curriculum with images.

**Request:**
- Content-Type: `multipart/form-data`
- Body: PDF file with key `pdf_file`

**Response:**
```json
{
  "success": true,
  "structured_course": {
    "course_info": {
      "course_title": "Course Name",
      "course_description": "Description",
      "pdf_filename": "document.pdf",
      "text_length": 1500
    },
    "course_cover_image": {
      "image_url": "https://ideogram.ai/...",
      "image_id": "uuid",
      "s3_url": "https://s3.amazonaws.com/...",
      "image_base64": "base64_encoded_image"
    },
    "modules": [
      {
        "module_number": 1,
        "module_title": "Module Title",
        "module_content": "Detailed module content...",
        "module_image": {
          "image_url": "https://ideogram.ai/...",
          "image_id": "uuid",
          "s3_url": "https://s3.amazonaws.com/...",
          "image_base64": "base64_encoded_image"
        }
      }
    ]
  },
  "raw_curriculum": {...},
  "extracted_text": "Original text from PDF..."
}
```

#### 2. **Health Check**
**GET** `/health`

Returns API status and health information.

#### 3. **Text Extraction Only**
**POST** `/extract-text`

Extract only text content from PDF without generating curriculum.

#### 4. **Image Generation Only**
**POST** `/generate-image`

Generate an image from text prompt.

### Lisa App Integration

#### 5. **Generate and Create Lisa Course** (Complete Workflow)
**POST** `/generate-and-create-lisa-course`

Complete end-to-end workflow: Generate curriculum, create Lisa course, and create all module slides.

**Request:**
- Content-Type: `multipart/form-data`
- Body:
  - `pdf_file`: PDF file
  - `org_id`: Organization ID
  - `uid`: User ID (optional, auto-generated if not provided)
  - `authorization_token`: Lisa authorization token

**Response:**
```json
{
  "success": true,
  "message": "Curriculum generated and Lisa course created successfully",
  "course_creation": {
    "success": true,
    "course_title": "Course Title",
    "cover_image_url": "https://s3.amazonaws.com/...",
    "result": {...}
  },
  "module_slides": {
    "total_modules": 5,
    "successful_slides": 5,
    "failed_slides": 0,
    "results": [...]
  },
  "structured_course": {...},
  "raw_curriculum": {...}
}
```

#### 6. **Create Lisa Course Only**
**POST** `/create-lisa-course`

Create only the Lisa course without modules.

**POST** `/create-lisa-course-with-s3`

Create Lisa course using S3 URLs from generated curriculum.

#### 7. **Create Module Slides**
**POST** `/create-module-slides`

Create slides for all modules in an existing course.

**POST** `/post-modules-to-course`

Post module slides to an existing Lisa course.

### JWT Token Management

#### 8. **Set JWT Token**
**POST** `/set-jwt-token`

Set JWT token for authenticated API requests.

**Request:**
```json
{
  "token": "your_jwt_token_here"
}
```

#### 9. **Get JWT Token Status**
**GET** `/get-jwt-token`

Check current JWT token status.

### Module Management

#### 10. **Post Module Data**
**POST** `/post-module`

Post a single module to your module API.

**POST** `/post-all-modules`

Post all modules from a generated curriculum to your module API.

### Utility Endpoints

#### 11. **Debug Module Images**
**POST** `/debug-module-images`

Test image generation for multiple modules.

#### 12. **Test JSON Serialization**
**GET** `/test-json-serialization`

Verify JSON serialization works with image URLs.

#### 13. **Validate Lisa Token**
**POST** `/validate-lisa-token`

Test if a Lisa token is valid.

#### 14. **Get Lisa Token Help**
**GET** `/get-lisa-token`

Get instructions for extracting Lisa token from browser.

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for curriculum generation | Yes |
| `IDEOGRAM_API_KEY` | Ideogram API key for image generation | Yes |
| `AWS_ACCESS_KEY_ID` | AWS access key for S3 | Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for S3 | Yes |
| `AWS_REGION` | AWS region (default: us-east-1) | No |
| `S3_BUCKET_NAME` | S3 bucket name for image storage | Yes |
| `LISA_AUTHORIZATION_TOKEN` | Lisa app authorization token | No |

### AWS S3 Setup

1. Create an S3 bucket for storing generated images
2. Configure CORS if needed for cross-origin access
3. Ensure proper IAM permissions for the bucket

### Ideogram API Setup

1. Sign up at [ideogram.ai](https://ideogram.ai)
2. Get your API key from the dashboard
3. The API uses Ideogram v3 with realistic style generation

## 📖 Usage Examples

### Using curl

```bash
# Generate curriculum only
curl -X POST -F "pdf_file=@your_document.pdf" \
  http://localhost:5001/generate-curriculum

# Complete workflow with Lisa integration
curl -X POST -F "pdf_file=@your_document.pdf" \
  -F "org_id=6511358aa1964e1f8da51e86" \
  -F "uid=C_V8JOP-202506261304" \
  -F "authorization_token=your_token" \
  http://localhost:5001/generate-and-create-lisa-course
```

### Using Python requests

```python
import requests

# Generate curriculum
url = "http://localhost:5001/generate-curriculum"
files = {"pdf_file": open("your_document.pdf", "rb")}

response = requests.post(url, files=files)
data = response.json()

# Access structured course
course_info = data["structured_course"]["course_info"]
modules = data["structured_course"]["modules"]

# Access images
cover_image = data["structured_course"]["course_cover_image"]
```

### Using the Web Interface

1. Open `http://localhost:5001` in your browser
2. Click "Choose PDF File" to select your document
3. Click "Generate Curriculum" to start the process
4. View the generated curriculum with images
5. Use the raw JSON for further processing

## 🏗️ Architecture

### Core Components

- **Flask Application**: Main web server and API endpoints
- **CurriculumGenerator Class**: Core business logic for curriculum generation
- **PDF Processing**: PyPDF2 for text extraction
- **AI Integration**: OpenAI GPT-4o-mini for curriculum generation
- **Image Generation**: Ideogram API for educational illustrations
- **Storage**: AWS S3 for permanent image storage
- **Lisa Integration**: Direct API calls to Lisa app

### Data Flow

1. **PDF Upload** → Text extraction using PyPDF2
2. **Text Processing** → AI-powered curriculum generation using OpenAI
3. **Image Generation** → Educational illustrations using Ideogram
4. **S3 Upload** → Permanent storage of generated images
5. **Lisa Integration** → Course and module creation in Lisa app

## 🧪 Testing

### Test Scripts

- **`create_sample_pdf.py`**: Creates sample PDFs for testing
- **`test_sample_pdf.py`**: Creates test PDFs with specific content
- **`get_lisa_token.py`**: Helps extract and validate Lisa tokens

### Manual Testing

```bash
# Create test PDF
python create_sample_pdf.py

# Test token validation
python get_lisa_token.py

# Run the application
python app.py
```

## 🚨 Error Handling

The API provides comprehensive error handling:

- **HTTP Status Codes**: Proper status codes for different error types
- **Error Messages**: Descriptive error messages for debugging
- **Logging**: Extensive logging for troubleshooting
- **Graceful Fallbacks**: Fallback mechanisms when services fail

### Common Error Scenarios

- Missing PDF file
- Invalid file format
- API key configuration issues
- S3 upload failures
- Lisa API authentication errors

## 🔒 Security Considerations

- **API Keys**: Store all API keys in environment variables
- **File Validation**: Only PDF files are accepted
- **Authentication**: JWT token management for secure access
- **CORS**: Configured for cross-origin requests
- **Input Validation**: Proper validation of all inputs

## 📊 Performance

- **Async Processing**: Non-blocking image generation
- **Caching**: S3 storage for generated images
- **Optimization**: Efficient PDF text extraction
- **Scalability**: Designed for production deployment

## 🚀 Deployment

### Production Considerations

1. **Environment Variables**: Secure configuration management
2. **Logging**: Production-grade logging configuration
3. **Monitoring**: Health check endpoints for monitoring
4. **Scaling**: Consider containerization for scaling

### Docker (Recommended)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5001

CMD ["python", "app.py"]
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues and questions:

1. Check the error logs in the application
2. Verify your API keys and configuration
3. Test individual endpoints for debugging
4. Check the Lisa app integration status

## 🔄 Changelog

### Current Version
- ✅ PDF text extraction with PyPDF2
- ✅ AI curriculum generation with OpenAI GPT-4o-mini
- ✅ Image generation with Ideogram API
- ✅ AWS S3 integration for image storage
- ✅ Complete Lisa app integration
- ✅ Web interface for easy usage
- ✅ Comprehensive API endpoints
- ✅ JWT token management
- ✅ Error handling and logging

---

**Built with ❤️ for educational content creators** 