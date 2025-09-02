from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import PyPDF2
import io
import base64
import uuid
import os
from dotenv import load_dotenv
import openai
import requests
from PIL import Image
import json
import re
import logging
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure OpenAI and Ideogram
openai.api_key = os.getenv('OPENAI_API_KEY')
ideogram_api_key = os.getenv('IDEOGRAM_API_KEY')

# Configure S3
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'lisa-research')

# Lisa API Token (optional - can be set in environment)
LISA_AUTHORIZATION_TOKEN = os.getenv('LISA_AUTHORIZATION_TOKEN')
logger.info(f"LISA_AUTHORIZATION_TOKEN loaded: {'YES' if LISA_AUTHORIZATION_TOKEN else 'NO'}")

class CurriculumGenerator:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))  # Still needed for text generation
        self.ideogram_api_key = ideogram_api_key
        self.jwt_token = None  # Will store the dynamic JWT token
        self.s3_client = s3_client
        self.s3_bucket = S3_BUCKET_NAME
    
    def extract_text_from_pdf(self, pdf_file):
        """Extract text from uploaded PDF file"""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
            # Log for debugging
            logger.info(f"Extracted text length: {len(text)} from {len(pdf_reader.pages)} pages.")
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise Exception(f"Error extracting text from PDF: {str(e)}")
    
    def split_sections(self, text):
        """Split text into modules based on numbered sections or topics"""
        # First try to split on numbered patterns like "1.", "2.", etc.
        numbered_pattern = r'(\d+\.\s*[^\n]+)'
        numbered_parts = re.split(numbered_pattern, text, flags=re.IGNORECASE)
        
        modules = []
        
        if len(numbered_parts) > 1:
            # Process numbered sections
            current_content = ""
            for i in range(1, len(numbered_parts), 2):
                if i < len(numbered_parts):
                    title = numbered_parts[i].strip()
                    # Get content until next numbered item or end
                    content_start = text.find(title) + len(title)
                    if i + 2 < len(numbered_parts):
                        next_title = numbered_parts[i + 2]
                        content_end = text.find(next_title, content_start)
                    else:
                        content_end = len(text)
                    
                    content = text[content_start:content_end].strip()
                    if content:
                        modules.append({'title': title, 'content': content})
                    else:
                        # If no content, use the title as content
                        modules.append({'title': title, 'content': title})
        
        # If no numbered sections found, try Part/Chapter/Section patterns
        if not modules:
            pattern = r'((?:Part|Chapter|Section)\s*\d+[:\s][^\n]*)'
            parts = re.split(pattern, text, flags=re.IGNORECASE)
            if len(parts) > 1:
                # The first part may be intro text
                intro = parts[0].strip()
                for i in range(1, len(parts), 2):
                    raw_title = parts[i].strip()
                    # Remove 'Part X:', 'Chapter X:', or 'Section X:' from the title
                    clean_title = re.sub(r'^(Part|Chapter|Section)\s*\d+[:\s]*', '', raw_title, flags=re.IGNORECASE).strip()
                    if not clean_title:
                        clean_title = f'Module {(i//2)+1}'
                    content = parts[i+1].strip() if i+1 < len(parts) else ""
                    modules.append({'title': clean_title, 'content': content})
        
        # If still no modules, treat the whole text as one module
        if not modules:
            modules.append({'title': 'Module 1', 'content': text.strip()})
        
        logger.info(f"Split text into {len(modules)} modules")
        for i, module in enumerate(modules):
            logger.info(f"Module {i+1}: {module['title'][:50]}...")
        
        return modules
    
    def generate_curriculum(self, text):
        """Generate curriculum from extracted text using OpenAI"""
        try:
            modules = self.split_sections(text)
            logger.info(f"Generated {len(modules)} modules from text")
            
            # Compose a prompt for the AI to expand each module and generate image prompts
            prompt = f"""
You will receive a list of course modules, each with a title and raw content. For the course:
- Generate a clear, descriptive, and engaging course title (do not leave blank).
- Generate a brief course description.
- Generate a highly detailed, realistic, and contextually accurate image prompt for the course cover image. The image prompt should visually represent the course topic, specifying key visual elements, educational context, and professional style. Ensure the image prompt is unique, descriptive, and suitable for high-quality, realistic educational illustrations.
For each module:
- Use the provided title as the module title (refine if needed).
- Generate a highly detailed, realistic, and contextually accurate image prompt for the module. The image prompt should visually represent the module's topic, specifying key visual elements, educational context, and professional style. Ensure each image prompt is unique, descriptive, and suitable for high-quality, realistic educational illustrations.
- Expand and elaborate on the module content, aiming for 350-400+ words per module. Include all relevant text, and add further explanation, examples, use cases, and key learning points to make the content comprehensive, engaging, and educational. Ensure all important concepts are covered and nothing essential is omitted.

Return a JSON with this structure:
{{
    "course_title": "Course Name (required)",
    "course_description": "Brief course description",
    "course_cover_image_prompt": "Professional course cover image showing [specific visual elements related to the course topic] with realistic lighting, modern design, and educational appeal",
    "modules": [
        {{
            "module_number": 1,
            "module_title": "Module Title",
            "module_image_prompt": "Highly detailed, realistic educational illustration showing [specific visual elements related to this module topic] with professional appearance, detailed graphics, and academic context",
            "module_content": "Very detailed text content for this module including key concepts, explanations, examples, use cases, and learning points"
        }}
    ]
}}

Here are the modules:
"""
            for idx, m in enumerate(modules):
                prompt += f"\nModule {idx+1} Title: {m['title']}\nModule {idx+1} Raw Content: {m['content']}\n"
            
            logger.info("Generating curriculum with OpenAI...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a curriculum development expert. Always return valid JSON. The course_title is required and must not be blank. Each module must have a title, a highly detailed, realistic image prompt, and very detailed text content (350-400+ words)."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )
            curriculum_text = response.choices[0].message.content
            logger.info("Curriculum generated successfully")
            

            ct = curriculum_text.strip()
            if ct.startswith('```json'):
                ct = ct[7:]
            if ct.startswith('```'):
                ct = ct[3:]
            if ct.endswith('```'):
                ct = ct[:-3]
            # Robustly parse the OpenAI response, even if double-encoded as a string
            try:
                parsed = ct
                for _ in range(2):
                    if isinstance(parsed, str):
                        parsed = json.loads(parsed)
                logger.info(f"Successfully parsed curriculum with {len(parsed.get('modules', []))} modules")
                return parsed
            except Exception as e:
                logger.error(f"Error parsing curriculum JSON: {str(e)}")
                return {"curriculum_text": curriculum_text}
                
        except Exception as e:
            logger.error(f"Error generating curriculum: {str(e)}")
            raise Exception(f"Error generating curriculum: {str(e)}")
    
    def generate_image(self, text, include_base64=True):
        """Generate image based on text using Ideogram only"""
        try:
            logger.info(f"Generating image for prompt: {text[:100]}...")
            
            # Enhanced prompt for more realistic images
            enhanced_prompt = f"""
            Create a highly realistic, professional educational illustration for: {text}
            
            Style requirements:
            - Photorealistic quality with high detail
            - Professional educational content appearance
            - Clean, modern design suitable for course materials
            - Realistic lighting and shadows
            - Professional color palette
            - No cartoon or abstract elements
            - Suitable for academic and professional learning environments
            - High-resolution, crisp details
            """
            
            # Check if Ideogram API key is configured
            if not self.ideogram_api_key:
                raise Exception("Ideogram API key not configured. Please set IDEOGRAM_API_KEY environment variable.")
            
            logger.info("Generating image with Ideogram...")
            
            # Use the correct Ideogram API endpoint
            ideogram_url = "https://api.ideogram.ai/v1/ideogram-v3/generate"
            
            headers = {
                "Api-Key": self.ideogram_api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "prompt": enhanced_prompt,
                "aspect_ratio": "1x1",  # Square aspect ratio
                "rendering_speed": "DEFAULT",  # Options: FLASH, TURBO, BALANCED, DEFAULT, QUALITY
                "style_type": "REALISTIC"  # Options: AUTO, GENERAL, REALISTIC, DESIGN, CUSTOM, FICTION
            }
            
            try:
                logger.info(f"Making request to Ideogram API: {ideogram_url}")
                response = requests.post(
                    url=ideogram_url,
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # Check if generation was successful
                    if response_data.get('data') and len(response_data['data']) > 0:
                        image_url = response_data['data'][0].get('url')
                        
                        if image_url:
                            logger.info(f"Image generated successfully with Ideogram: {image_url}")
                            
                            result = {
                                "image_url": image_url,
                                "image_id": str(uuid.uuid4()),
                                "prompt_used": enhanced_prompt,
                                "provider": "ideogram"
                            }
                            
                            # Only include base64 if requested
                            if include_base64:
                                # Download and convert to base64
                                img_response = requests.get(image_url, timeout=30)
                                img_response.raise_for_status()  # Raise exception for bad status codes
                                img_data = base64.b64encode(img_response.content).decode('utf-8')
                                result["image_base64"] = img_data
                                logger.info(f"Image processed successfully, size: {len(img_data)} chars")
                            else:
                                logger.info("Image URL generated (base64 excluded)")
                            
                            return result
                        else:
                            raise Exception("No image URL returned from Ideogram")
                    else:
                        raise Exception(f"Ideogram generation failed: {response_data}")
                else:
                    error_msg = f"Ideogram API request failed with status {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                    
            except Exception as e:
                error_msg = f"Error generating image with Ideogram: {str(e)}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            raise Exception(f"Error generating image: {str(e)}")
    
    def upload_image_to_s3(self, image_url, image_id, image_type="module"):
        """Upload image from URL to S3 and return the S3 URL"""
        try:
            logger.info(f"Uploading {image_type} image to S3: {image_id}")
            
            # Download image from URL
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Generate S3 key
            s3_key = f"courses/{image_id}.png"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=response.content,
                ContentType='image/png'
            )
            
            # Generate S3 URL
            s3_url = f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}"
            logger.info(f"Image uploaded to S3: {s3_url}")
            
            return s3_url
            
        except Exception as e:
            logger.error(f"Error uploading image to S3: {str(e)}")
            raise Exception(f"Error uploading image to S3: {str(e)}")
    

    
    def set_jwt_token(self, token):
        """Set the JWT token for API requests"""
        self.jwt_token = token
        logger.info("JWT token set successfully")
    
    def get_jwt_token(self):
        """Get the current JWT token"""
        return self.jwt_token
    
    def make_authenticated_post_request(self, url, data=None, json_data=None, headers=None):
        """Make a POST request with JWT authorization header"""
        try:
            if not self.jwt_token:
                raise Exception("JWT token not set. Call set_jwt_token() first.")
            
            # Prepare headers with JWT authorization
            request_headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.jwt_token}'
            }
            
            # Add any additional headers
            if headers:
                request_headers.update(headers)
            
            logger.info(f"Making authenticated POST request to: {url}")
            logger.info(f"Headers: {request_headers}")
            
            # Make the request
            response = requests.post(
                url=url,
                data=data,
                json=json_data,
                headers=request_headers,
                timeout=30
            )
            
            # Log response status
            logger.info(f"Response status: {response.status_code}")
            
            # Check if request was successful
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                response_data = response.json()
                logger.info("Request successful, JSON response received")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response_data
                }
            except ValueError:
                # If response is not JSON, return text
                logger.info("Request successful, text response received")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.text
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
            }
        except Exception as e:
            logger.error(f"Unexpected error in POST request: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def post_module_data(self, module_data, api_url):
        """Post module data with text and image to the module API"""
        try:
            if not self.jwt_token:
                raise Exception("JWT token not set. Call set_jwt_token() first.")
            
            # Prepare the data for the module API
            post_data = {
                "module_title": module_data.get("module_title", ""),
                "module_content": module_data.get("module_content", ""),
                "module_image_url": module_data.get("module_image", {}).get("image_url", ""),
                "module_number": module_data.get("module_number", 1)
            }
            
            logger.info(f"Posting module data to: {api_url}")
            logger.info(f"Module title: {post_data['module_title']}")
            
            # Make the authenticated POST request
            result = self.make_authenticated_post_request(
                url=api_url,
                json_data=post_data
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error posting module data: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_lisa_course(self, course_title, cover_image_url, org_id, uid, authorization_token):
        """Create a Lisa course with the given parameters"""
        try:
            logger.info(f"Creating Lisa course: {course_title}")
            
            # Prepare the course data
            course_data = {
                "title": course_title,
                "details": "",
                "uid": uid,
                "orgId": org_id,
                "mode": "offline",
                "type": "C",
                "duration": {
                    "duration": 30
                },
                "supportedLanguages": "en_US",
                "icon": None,
                "coverImage": cover_image_url
            }
            
            logger.info(f"Course data being sent: {course_data}")
            
            # Make the API request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {authorization_token}'
            }
            
            response = requests.post(
                'https://admin.lisaapp.net/v1/cohort/new',
                json=course_data,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Lisa course creation response status: {response.status_code}")
            logger.info(f"Lisa course creation response: {response.text}")
            
            if response.status_code == 200 or response.status_code == 201:
                response_data = response.json()
                logger.info(f"Lisa course created successfully. Response: {response_data}")
                return response_data
            else:
                error_msg = f"Failed to create Lisa course. Status: {response.status_code}, Response: {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Error creating Lisa course: {str(e)}")
            raise Exception(f"Error creating Lisa course: {str(e)}")
    
    def verify_course_exists(self, course_id, authorization_token):
        """Verify if a course exists in Lisa by making a GET request"""
        try:
            logger.info(f"Verifying course exists: {course_id}")
            
            headers = {
                'Authorization': f'Bearer {authorization_token}'
            }
            
            # Try to get course details
            response = requests.get(
                f'https://admin.lisaapp.net/v1/cohort/{course_id}',
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Course verification response status: {response.status_code}")
            logger.info(f"Course verification response: {response.text}")
            
            if response.status_code == 200:
                logger.info(f"Course {course_id} exists and is accessible")
                return True
            else:
                logger.warning(f"Course {course_id} not found or not accessible. Status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying course: {str(e)}")
            return False
    
    def create_module_slide(self, module_title, module_content, image_url, course_id, authorization_token):
        """Create a module slide in Lisa app using the course ID"""
        try:
            logger.info(f"Creating module slide: {module_title} for course: {course_id}")
            
            # Prepare the slide data
            slide_data = {
                "type": "default",
                "title": {
                    "text": module_title,
                    "color": None,
                    "alignment": {
                        "horizontal": "start",
                        "vertical": "center"
                    },
                    "weight": 600,
                    "italics": False
                },
                "description": {
                    "text": module_content,
                    "color": None,
                    "alignment": {
                        "horizontal": "start",
                        "vertical": "center"
                    },
                    "weight": 400,
                    "italics": False
                },
                "textContainerSize": "auto",
                "backgroundColor": None,
                "media": {
                    "type": "image",
                    "url": image_url,
                    "alignment": "fullscreen"
                },
                "options": [],
                "assessmentPrompt": "",
                "restrictScroll": False,
                "maxDuration": 0
            }
            
            # Make the API request using course_id instead of org_id
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {authorization_token}'
            }
            
            response = requests.post(
                f'https://admin.lisaapp.net/v2/slides/cohort/{course_id}',
                json=slide_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200 or response.status_code == 201:
                logger.info(f"Module slide created successfully: {module_title}")
                return response.json()
            else:
                error_msg = f"Failed to create module slide. Status: {response.status_code}, Response: {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"Error creating module slide: {str(e)}")
            raise Exception(f"Error creating module slide: {str(e)}")

# Initialize curriculum generator
curriculum_generator = CurriculumGenerator()

@app.route('/')
def index():
    """Serve the main HTML interface"""
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Curriculum API is running"})

@app.route('/generate-curriculum', methods=['POST'])
def generate_curriculum():
    """Main endpoint to process PDF and generate curriculum with images"""
    try:
        logger.info("Starting curriculum generation process")
        
        # Check if PDF file is provided
        if 'pdf_file' not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf_file']
        
        if pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        logger.info(f"Processing PDF: {pdf_file.filename}")
        
        # Extract text from PDF
        pdf_content = io.BytesIO(pdf_file.read())
        extracted_text = curriculum_generator.extract_text_from_pdf(pdf_content)
        
        if not extracted_text.strip():
            return jsonify({"error": "No text could be extracted from the PDF"}), 400
        
        # Generate curriculum
        curriculum = curriculum_generator.generate_curriculum(extracted_text)
        
        # Initialize structured course content
        structured_course = {
            "course_info": {},
            "course_cover_image": {},
            "modules": []
        }
        
        if isinstance(curriculum, dict):
            logger.info("Processing structured curriculum")
            
            # Extract course information
            structured_course["course_info"] = {
                "course_title": curriculum.get('course_title', 'Untitled Course'),
                "course_description": curriculum.get('course_description', ''),
                "pdf_filename": pdf_file.filename,
                "text_length": len(extracted_text)
            }
            
            # Generate course cover image
            cover_prompt = curriculum.get('course_cover_image_prompt', curriculum.get('course_title', 'Course Cover'))
            logger.info(f"Generating course cover image with prompt: {cover_prompt[:100]}...")
            course_cover_image = None
            try:
                course_cover_image = curriculum_generator.generate_image(cover_prompt, include_base64=True)
                
                # Upload cover image to S3
                if course_cover_image and "image_url" in course_cover_image:
                    s3_cover_url = curriculum_generator.upload_image_to_s3(
                        course_cover_image["image_url"], 
                        course_cover_image["image_id"], 
                        "cover"
                    )
                    course_cover_image["s3_url"] = s3_cover_url
                    logger.info(f"Course cover image uploaded to S3: {s3_cover_url}")
                
                structured_course["course_cover_image"] = course_cover_image
                logger.info("Course cover image generated successfully")
            except Exception as e:
                logger.error(f"Error generating course cover image: {str(e)}")
                structured_course["course_cover_image"] = {"error": str(e)}
            
            # Generate images and content for each module
            modules = curriculum.get('modules', [])
            logger.info(f"Generating images for {len(modules)} modules")
            
            for i, module in enumerate(modules):
                logger.info(f"Processing module {i+1}: {module.get('module_title', f'Module {i+1}')}")
                
                module_data = {
                    "module_number": module.get('module_number', i + 1),
                    "module_title": module.get('module_title', f'Module {i + 1}'),
                    "module_image": {},
                    "module_content": module.get('module_content', '')
                }
                
                # Generate module image
                image_prompt = module.get('module_image_prompt', module.get('module_title', f'Module {i + 1}'))
                logger.info(f"Generating image for module {i+1} with prompt: {image_prompt[:100]}...")
                module_image = None
                try:
                    module_image = curriculum_generator.generate_image(image_prompt, include_base64=True)
                    
                    # Upload module image to S3
                    if module_image and "image_url" in module_image:
                        s3_module_url = curriculum_generator.upload_image_to_s3(
                            module_image["image_url"], 
                            module_image["image_id"], 
                            "module"
                        )
                        module_image["s3_url"] = s3_module_url
                        logger.info(f"Module {i+1} image uploaded to S3: {s3_module_url}")
                    
                    module_data["module_image"] = module_image
                    logger.info(f"Module {i+1} image generated successfully")
                    logger.info(f"Module {i+1} image URL: {module_image.get('image_url', 'No URL')}")
                    logger.info(f"Module {i+1} image ID: {module_image.get('image_id', 'No ID')}")
                except Exception as e:
                    logger.error(f"Error generating image for module {i+1}: {str(e)}")
                    module_data["module_image"] = {"error": str(e)}
                
                structured_course["modules"].append(module_data)
                logger.info(f"Module {i+1} data added to structured course")
                
                # Inject image_url into raw_curriculum (curriculum['modules']) for frontend raw JSON
                if "modules" in curriculum and i < len(curriculum["modules"]):
                    if module_image and "image_url" in module_image:
                        curriculum["modules"][i]["generated_image_url"] = module_image.get("image_url", "")
                    else:
                        curriculum["modules"][i]["generated_image_url"] = ""
            
            logger.info(f"Total modules processed: {len(structured_course['modules'])}")
            logger.info(f"Sample module image data: {structured_course['modules'][0].get('module_image', 'No image data') if structured_course['modules'] else 'No modules'}")
        else:
            logger.warning("Curriculum generation failed, using fallback")
            # Fallback if curriculum generation failed
            structured_course["course_info"] = {
                "course_title": "Generated Course",
                "course_description": "Course generated from PDF content",
                "pdf_filename": pdf_file.filename,
                "text_length": len(extracted_text)
            }
            structured_course["course_cover_image"] = {"error": "Curriculum generation failed"}
        
        # Prepare response
        response_data = {
            "success": True,
            "structured_course": structured_course,
            "raw_curriculum": curriculum,
            "extracted_text": extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
        }
        
        # Debug: Log the structure of the response
        logger.info("=== RESPONSE DEBUG INFO ===")
        logger.info(f"Structured course keys: {list(structured_course.keys())}")
        logger.info(f"Number of modules in structured course: {len(structured_course.get('modules', []))}")
        
        if structured_course.get('modules'):
            for i, module in enumerate(structured_course['modules']):
                logger.info(f"Module {i+1} keys: {list(module.keys())}")
                logger.info(f"Module {i+1} image keys: {list(module.get('module_image', {}).keys())}")
                if 'image_url' in module.get('module_image', {}):
                    logger.info(f"Module {i+1} has image URL: {module['module_image']['image_url'][:50]}...")
                else:
                    logger.info(f"Module {i+1} has NO image URL")
        
        logger.info("=== END RESPONSE DEBUG ===")
        logger.info("Curriculum generation completed successfully")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in generate-curriculum endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/extract-text', methods=['POST'])
def extract_text_only():
    """Endpoint to only extract text from PDF"""
    try:
        if 'pdf_file' not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf_file']
        pdf_content = io.BytesIO(pdf_file.read())
        extracted_text = curriculum_generator.extract_text_from_pdf(pdf_content)
        
        return jsonify({
            "success": True,
            "extracted_text": extracted_text,
            "text_length": len(extracted_text)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate-image', methods=['POST'])
def generate_image_only():
    """Endpoint to generate image from text"""
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({"error": "Text is required"}), 400
        
        text = data['text']
        size = data.get('size', '1024x1024')
        
        image_data = curriculum_generator.generate_image(text)
        
        return jsonify({
            "success": True,
            "image": image_data
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/debug-module-images', methods=['POST'])
def debug_module_images():
    """Debug endpoint to test module image generation"""
    try:
        data = request.get_json()
        if not data or 'modules' not in data:
            return jsonify({"error": "Modules data is required"}), 400
        
        modules = data['modules']
        logger.info(f"Debug: Testing image generation for {len(modules)} modules")
        
        results = []
        for i, module in enumerate(modules):
            module_info = {
                "module_number": i + 1,
                "module_title": module.get('module_title', f'Module {i+1}'),
                "image_prompt": module.get('module_image_prompt', ''),
                "image_result": {}
            }
            
            # Test image generation
            image_prompt = module.get('module_image_prompt', module.get('module_title', f'Module {i+1}'))
            logger.info(f"Debug: Generating image for module {i+1}: {image_prompt[:50]}...")
            
            try:
                image_data = curriculum_generator.generate_image(image_prompt)
                module_info["image_result"] = {
                    "success": True,
                    "image_url": image_data["image_url"],
                    "image_id": image_data["image_id"],
                    "base64_length": len(image_data["image_base64"])
                }
                logger.info(f"Debug: Module {i+1} image generated successfully")
            except Exception as e:
                module_info["image_result"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"Debug: Error generating image for module {i+1}: {str(e)}")
            
            results.append(module_info)
        
        return jsonify({
            "success": True,
            "debug_results": results
        })
        
    except Exception as e:
        logger.error(f"Error in debug module images: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/test-json-serialization', methods=['GET'])
def test_json_serialization():
    """Test endpoint to verify JSON serialization works with image URLs"""
    try:
        # Create a test structure similar to what we're returning
        test_data = {
            "success": True,
            "structured_course": {
                "course_info": {
                    "course_title": "Test Course"
                },
                "course_cover_image": {
                    "image_url": "https://oaidalleapiprodscus.blob.core.windows.net/test-image.jpg",
                    "image_id": "test-uuid-123",
                    "prompt_used": "Test prompt"
                },
                "modules": [
                    {
                        "module_number": 1,
                        "module_title": "Test Module",
                        "module_content": "Test content",
                        "module_image": {
                            "image_url": "https://oaidalleapiprodscus.blob.core.windows.net/test-module-image.jpg",
                            "image_id": "test-module-uuid-456",
                            "prompt_used": "Test module prompt"
                        }
                    }
                ]
            }
        }
        
        logger.info("Testing JSON serialization...")
        logger.info(f"Test data structure: {list(test_data.keys())}")
        logger.info(f"Modules in test data: {len(test_data['structured_course']['modules'])}")
        logger.info(f"Module image URL: {test_data['structured_course']['modules'][0]['module_image']['image_url']}")
        
        return jsonify(test_data)
        
    except Exception as e:
        logger.error(f"Error in test JSON serialization: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/set-jwt-token', methods=['POST'])
def set_jwt_token():
    """Set the JWT token for API requests"""
    try:
        data = request.get_json()
        if not data or 'token' not in data:
            return jsonify({"error": "JWT token is required"}), 400
        
        token = data['token']
        curriculum_generator.set_jwt_token(token)
        
        return jsonify({
            "success": True,
            "message": "JWT token set successfully"
        })
        
    except Exception as e:
        logger.error(f"Error setting JWT token: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get-jwt-token', methods=['GET'])
def get_jwt_token():
    """Get the current JWT token status"""
    try:
        token = curriculum_generator.get_jwt_token()
        
        return jsonify({
            "success": True,
            "token_set": token is not None,
            "token_length": len(token) if token else 0
        })
        
    except Exception as e:
        logger.error(f"Error getting JWT token: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/post-module', methods=['POST'])
def post_module():
    """Post a single module to the module API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Module data is required"}), 400
        
        # Check if JWT token is set
        if not curriculum_generator.get_jwt_token():
            return jsonify({"error": "JWT token not set. Call /set-jwt-token first."}), 400
        
        # Get the module API URL from request
        api_url = data.get('api_url')
        if not api_url:
            return jsonify({"error": "API URL is required"}), 400
        
        # Extract module data
        module_data = data.get('module_data', {})
        if not module_data:
            return jsonify({"error": "Module data is required"}), 400
        
        # Post the module
        result = curriculum_generator.post_module_data(module_data, api_url)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error posting module: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/post-all-modules', methods=['POST'])
def post_all_modules():
    """Post all modules from a generated curriculum to the module API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data is required"}), 400
        
        # Check if JWT token is set
        if not curriculum_generator.get_jwt_token():
            return jsonify({"error": "JWT token not set. Call /set-jwt-token first."}), 400
        
        # Get the module API URL from request
        api_url = data.get('api_url')
        if not api_url:
            return jsonify({"error": "API URL is required"}), 400
        
        # Get the structured course data
        structured_course = data.get('structured_course', {})
        modules = structured_course.get('modules', [])
        
        if not modules:
            return jsonify({"error": "No modules found in structured course"}), 400
        
        logger.info(f"Posting {len(modules)} modules to: {api_url}")
        
        results = []
        for i, module in enumerate(modules):
            logger.info(f"Posting module {i+1}/{len(modules)}: {module.get('module_title', f'Module {i+1}')}")
            
            result = curriculum_generator.post_module_data(module, api_url)
            result['module_number'] = i + 1
            result['module_title'] = module.get('module_title', f'Module {i+1}')
            results.append(result)
            
            # Add a small delay between requests to avoid overwhelming the API
            import time
            time.sleep(0.5)
        
        # Count successful and failed posts
        successful = sum(1 for r in results if r.get('success', False))
        failed = len(results) - successful
        
        return jsonify({
            "success": True,
            "total_modules": len(modules),
            "successful_posts": successful,
            "failed_posts": failed,
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Error posting all modules: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/create-lisa-course', methods=['POST'])
def create_lisa_course():
    """Create a course in Lisa app using the generated curriculum data"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data is required"}), 400
        
        # Get required parameters
        org_id = data.get('org_id')
        uid = data.get('uid')
        authorization_token = data.get('authorization_token')
        
        if not org_id:
            return jsonify({"error": "org_id is required"}), 400
        if not uid:
            return jsonify({"error": "uid is required"}), 400
        if not authorization_token:
            return jsonify({"error": "authorization_token is required"}), 400
        
        # Get the structured course data
        structured_course = data.get('structured_course', {})
        course_info = structured_course.get('course_info', {})
        course_cover_image = structured_course.get('course_cover_image', {})
        
        # Extract course title and cover image (prefer S3 URL)
        course_title = course_info.get('course_title', 'Untitled Course')
        cover_image_url = course_cover_image.get('s3_url') or course_cover_image.get('image_url', '')
        
        if not cover_image_url:
            return jsonify({"error": "Course cover image URL is required"}), 400
        
        logger.info(f"Creating Lisa course with title: {course_title}")
        logger.info(f"Organization ID: {org_id}")
        logger.info(f"UID: {uid}")
        logger.info(f"Cover image URL: {cover_image_url}")
        
        # Create the Lisa course
        result = curriculum_generator.create_lisa_course(
            course_title=course_title,
            cover_image_url=cover_image_url,
            org_id=org_id,
            uid=uid,
            authorization_token=authorization_token
        )
        
        return jsonify({
            "success": True,
            "course_title": course_title,
            "cover_image_url": cover_image_url,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error creating Lisa course: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/create-lisa-course-with-s3', methods=['POST'])
def create_lisa_course_with_s3():
    """Create a Lisa course using S3 URLs from generated curriculum"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract required fields
        structured_course = data.get('structured_course')
        org_id = data.get('org_id')
        uid = data.get('uid')
        authorization_token = data.get('authorization_token')
        
        if not all([structured_course, org_id, uid, authorization_token]):
            return jsonify({"error": "Missing required fields: structured_course, org_id, uid, authorization_token"}), 400
        
        # Get course title and S3 cover image URL
        course_title = structured_course.get('course_info', {}).get('course_title', 'Untitled Course')
        cover_image_data = structured_course.get('course_cover_image', {})
        
        # Use S3 URL if available, otherwise use original URL
        cover_image_url = cover_image_data.get('s3_url') or cover_image_data.get('image_url')
        
        if not cover_image_url:
            return jsonify({"error": "No cover image URL available"}), 400
        
        # Create the Lisa course
        result = curriculum_generator.create_lisa_course(
            course_title=course_title,
            cover_image_url=cover_image_url,
            org_id=org_id,
            uid=uid,
            authorization_token=authorization_token
        )
        
        return jsonify({
            "success": True,
            "course_title": course_title,
            "cover_image_url": cover_image_url,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error in create-lisa-course-with-s3 endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/create-lisa-course-only', methods=['POST'])
def create_lisa_course_only():
    """Create only the Lisa course (without modules)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract required fields
        course_title = data.get('course_title')
        cover_image_url = data.get('cover_image_url')
        org_id = data.get('org_id')
        uid = data.get('uid')
        authorization_token = data.get('authorization_token')
        
        if not all([course_title, cover_image_url, org_id, uid, authorization_token]):
            return jsonify({"error": "Missing required fields: course_title, cover_image_url, org_id, uid, authorization_token"}), 400
        
        # Create the Lisa course
        result = curriculum_generator.create_lisa_course(
            course_title=course_title,
            cover_image_url=cover_image_url,
            org_id=org_id,
            uid=uid,
            authorization_token=authorization_token
        )
        
        return jsonify({
            "success": True,
            "course_title": course_title,
            "cover_image_url": cover_image_url,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error in create-lisa-course-only endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/create-module-slides', methods=['POST'])
def create_module_slides():
    """Create slides for all modules in a course"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract required fields
        modules = data.get('modules', [])
        course_id = data.get('course_id')  # Changed from org_id to course_id
        authorization_token = data.get('authorization_token')
        
        if not all([modules, course_id, authorization_token]):
            return jsonify({"error": "Missing required fields: modules, course_id, authorization_token"}), 400
        
        if not modules:
            return jsonify({"error": "No modules provided"}), 400
        
        logger.info(f"Creating slides for {len(modules)} modules")
        
        results = []
        for i, module in enumerate(modules):
            module_title = module.get('module_title', f'Module {i+1}')
            module_content = module.get('module_content', '')
            module_image = module.get('module_image', {})
            
            # Use S3 URL if available, otherwise use original URL
            image_url = module_image.get('s3_url') or module_image.get('image_url')
            
            if not image_url:
                logger.warning(f"No image URL for module {i+1}: {module_title}")
                continue
            
            try:
                result = curriculum_generator.create_module_slide(
                    module_title=module_title,
                    module_content=module_content,
                    image_url=image_url,
                    course_id=course_id,  # Changed from org_id to course_id
                    authorization_token=authorization_token
                )
                
                results.append({
                    "module_number": i + 1,
                    "module_title": module_title,
                    "success": True,
                    "result": result
                })
                
                logger.info(f"Module slide {i+1} created successfully: {module_title}")
                
            except Exception as e:
                logger.error(f"Error creating slide for module {i+1}: {str(e)}")
                results.append({
                    "module_number": i + 1,
                    "module_title": module_title,
                    "success": False,
                    "error": str(e)
                })
        
        # Count successful and failed creations
        successful = sum(1 for r in results if r.get('success', False))
        failed = len(results) - successful
        
        return jsonify({
            "success": True,
            "total_modules": len(modules),
            "successful_slides": successful,
            "failed_slides": failed,
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Error in create-module-slides endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/validate-lisa-token', methods=['POST'])
def validate_lisa_token():
    """Validate if a Lisa token is working"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        authorization_token = data.get('authorization_token')
        if not authorization_token:
            return jsonify({"error": "No authorization_token provided"}), 400
        
        # Test the token with a simple API call
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {authorization_token}'
        }
        
        # Try to get user info or any simple endpoint
        response = requests.get(
            'https://admin.lisaapp.net/v1/user/profile',  # or any other endpoint
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return jsonify({
                "success": True,
                "message": "Token is valid!",
                "status_code": response.status_code,
                "response": response.json()
            })
        else:
            return jsonify({
                "success": False,
                "message": "Token validation failed",
                "status_code": response.status_code,
                "response": response.text
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error validating token: {str(e)}"
        }), 500

@app.route('/get-lisa-token', methods=['GET'])
def get_lisa_token():
    """Helper endpoint to get Lisa token from browser storage"""
    return jsonify({
        "message": "To get your Lisa token:",
        "steps": [
            "1. Open Lisa app in browser",
            "2. Press F12 to open Developer Tools", 
            "3. Go to Application/Storage tab",
            "4. Look for 'lisa_access' in Local Storage",
            "5. Copy the token value",
            "6. Use it in your API calls"
        ],
        "example_usage": {
            "endpoint": "/generate-and-create-lisa-course",
            "method": "POST",
            "form_data": {
                "pdf_file": "your_file.pdf",
                "org_id": "6511358aa1964e1f8da51e86", 
                "uid": "C_V8JOP-202506261304",
                "authorization_token": "YOUR_TOKEN_HERE"
            }
        }
    })

@app.route('/generate-and-create-lisa-course', methods=['POST'])
def generate_and_create_lisa_course():
    """Generate curriculum and automatically create Lisa course + module slides"""
    try:
        logger.info("Starting automatic curriculum generation and Lisa course creation")
        
        # Check if PDF file is provided
        if 'pdf_file' not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf_file']
        
        if pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Get Lisa course parameters
        org_id = request.form.get('org_id')
        uid = request.form.get('uid')
        authorization_token = request.form.get('authorization_token')
        
        # Use environment token if not provided in request
        if not authorization_token and LISA_AUTHORIZATION_TOKEN:
            authorization_token = LISA_AUTHORIZATION_TOKEN
            logger.info("Using authorization token from environment variables")
        elif not authorization_token:
            return jsonify({"error": "No authorization_token provided and no LISA_AUTHORIZATION_TOKEN in environment"}), 400
        
        # Generate unique UID if not provided or if it already exists
        if not uid:
            import datetime
            uid = f"C_V8JOP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info(f"Generated unique UID: {uid}")
        
        if not org_id:
            return jsonify({"error": "Missing required field: org_id"}), 400
        
        logger.info(f"Processing PDF: {pdf_file.filename}")
        
        # Step 1: Extract text from PDF
        pdf_content = io.BytesIO(pdf_file.read())
        extracted_text = curriculum_generator.extract_text_from_pdf(pdf_content)
        
        if not extracted_text.strip():
            return jsonify({"error": "No text could be extracted from the PDF"}), 400
        
        # Step 2: Generate curriculum
        curriculum = curriculum_generator.generate_curriculum(extracted_text)
        
        # Step 3: Initialize structured course content
        structured_course = {
            "course_info": {},
            "course_cover_image": {},
            "modules": []
        }
        
        if isinstance(curriculum, dict):
            logger.info("Processing structured curriculum")
            
            # Extract course information
            structured_course["course_info"] = {
                "course_title": curriculum.get('course_title', 'Untitled Course'),
                "course_description": curriculum.get('course_description', ''),
                "pdf_filename": pdf_file.filename,
                "text_length": len(extracted_text)
            }
            
            # Generate course cover image
            cover_prompt = curriculum.get('course_cover_image_prompt', curriculum.get('course_title', 'Course Cover'))
            logger.info(f"Generating course cover image with prompt: {cover_prompt[:100]}...")
            course_cover_image = None
            try:
                course_cover_image = curriculum_generator.generate_image(cover_prompt, include_base64=True)
                
                # Upload cover image to S3
                if course_cover_image and "image_url" in course_cover_image:
                    s3_cover_url = curriculum_generator.upload_image_to_s3(
                        course_cover_image["image_url"], 
                        course_cover_image["image_id"], 
                        "cover"
                    )
                    course_cover_image["s3_url"] = s3_cover_url
                    logger.info(f"Course cover image uploaded to S3: {s3_cover_url}")
                
                structured_course["course_cover_image"] = course_cover_image
                logger.info("Course cover image generated successfully")
            except Exception as e:
                logger.error(f"Error generating course cover image: {str(e)}")
                structured_course["course_cover_image"] = {"error": str(e)}
            
            # Generate images and content for each module
            modules = curriculum.get('modules', [])
            logger.info(f"Generating images for {len(modules)} modules")
            
            for i, module in enumerate(modules):
                logger.info(f"Processing module {i+1}: {module.get('module_title', f'Module {i+1}')}")
                
                module_data = {
                    "module_number": module.get('module_number', i + 1),
                    "module_title": module.get('module_title', f'Module {i + 1}'),
                    "module_image": {},
                    "module_content": module.get('module_content', '')
                }
                
                # Generate module image
                image_prompt = module.get('module_image_prompt', module.get('module_title', f'Module {i + 1}'))
                logger.info(f"Generating image for module {i+1} with prompt: {image_prompt[:100]}...")
                module_image = None
                try:
                    module_image = curriculum_generator.generate_image(image_prompt, include_base64=True)
                    
                    # Upload module image to S3
                    if module_image and "image_url" in module_image:
                        s3_module_url = curriculum_generator.upload_image_to_s3(
                            module_image["image_url"], 
                            module_image["image_id"], 
                            "module"
                        )
                        module_image["s3_url"] = s3_module_url
                        logger.info(f"Module {i+1} image uploaded to S3: {s3_module_url}")
                    
                    module_data["module_image"] = module_image
                    logger.info(f"Module {i+1} image generated successfully")
                    logger.info(f"Module {i+1} image URL: {module_image.get('image_url', 'No URL')}")
                    logger.info(f"Module {i+1} image ID: {module_image.get('image_id', 'No ID')}")
                except Exception as e:
                    logger.error(f"Error generating image for module {i+1}: {str(e)}")
                    module_data["module_image"] = {"error": str(e)}
                
                structured_course["modules"].append(module_data)
                logger.info(f"Module {i+1} data added to structured course")
            
            # Step 4: Create Lisa Course
            logger.info("Creating Lisa course...")
            course_title = structured_course["course_info"]["course_title"]
            cover_image_url = structured_course["course_cover_image"].get('s3_url') or structured_course["course_cover_image"].get('image_url')
            
            if not cover_image_url:
                return jsonify({"error": "No cover image URL available for course creation"}), 400
            
            course_id = None
            # Try to create course with retry mechanism for UID conflicts
            max_retries = 3
            course_result = None
            course_id = None
            
            for attempt in range(max_retries):
                try:
                    # Generate new UID for retry attempts
                    if attempt > 0:
                        import datetime
                        import random
                        uid = f"C_V8JOP-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
                        logger.info(f"Retry attempt {attempt + 1}: Using new UID: {uid}")
                    
                    course_result = curriculum_generator.create_lisa_course(
                        course_title=course_title,
                        cover_image_url=cover_image_url,
                        org_id=org_id,
                        uid=uid,
                        authorization_token=authorization_token
                    )
                    logger.info("Lisa course created successfully")
                    
                    # Extract course ID from the response
                    if isinstance(course_result, dict):
                        logger.info(f"Course creation response: {course_result}")
                        
                        # Try to extract from the nested structure based on the actual response format
                        results = course_result.get('results', {})
                        data = results.get('data', {})
                        cohort_details = data.get('cohortDetails', {})
                        
                        # Try different possible keys for course ID
                        course_id = (cohort_details.get('_id') or 
                                   cohort_details.get('id') or 
                                   course_result.get('id') or 
                                   course_result.get('courseId') or 
                                   course_result.get('cohortId') or
                                   course_result.get('_id') or
                                   course_result.get('data', {}).get('id') or
                                   course_result.get('data', {}).get('courseId') or
                                   course_result.get('data', {}).get('cohortId'))
                        
                        if course_id:
                            logger.info(f"Extracted course ID: {course_id}")
                        else:
                            logger.warning("Could not extract course ID from response. Using org_id as fallback.")
                            course_id = org_id
                    else:
                        logger.warning(f"Course creation response is not a dict: {type(course_result)}. Using org_id as fallback.")
                        course_id = org_id
                    
                    # If we get here, course creation was successful
                    break
                    
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg and attempt < max_retries - 1:
                        logger.warning(f"UID conflict on attempt {attempt + 1}, retrying with new UID...")
                        continue
                    else:
                        logger.error(f"Error creating Lisa course: {error_msg}")
                        return jsonify({"error": f"Failed to create Lisa course: {error_msg}"}), 500
            
            # Verify course was actually created
            if course_id and course_id != org_id:
                logger.info(f"Verifying course creation with ID: {course_id}")
                course_exists = curriculum_generator.verify_course_exists(course_id, authorization_token)
                if not course_exists:
                    logger.warning(f"Course {course_id} was not found in Lisa system. Course creation may have failed.")
                    return jsonify({
                        "error": f"Course creation appeared successful but course {course_id} was not found in Lisa system",
                        "course_id": course_id,
                        "suggestion": "Check your Lisa admin interface or try again with a different UID"
                    }), 500
                else:
                    logger.info(f"Course {course_id} verified successfully in Lisa system")
            else:
                logger.warning("No valid course ID extracted. Course creation may have failed.")
                return jsonify({
                    "error": "Course creation failed - no valid course ID returned",
                    "course_result": course_result
                }), 500
            
            # Step 5: Create Module Slides
            logger.info(f"Creating module slides using course ID: {course_id}")
            slides_results = []
            successful_slides = 0
            failed_slides = 0
            
            for i, module in enumerate(structured_course["modules"]):
                module_title = module.get('module_title', f'Module {i+1}')
                module_content = module.get('module_content', '')
                module_image = module.get('module_image', {})
                
                # Use S3 URL if available, otherwise use original URL
                image_url = module_image.get('s3_url') or module_image.get('image_url')
                
                if not image_url:
                    logger.warning(f"No image URL for module {i+1}: {module_title}")
                    failed_slides += 1
                    slides_results.append({
                        "module_number": i + 1,
                        "module_title": module_title,
                        "success": False,
                        "error": "No image URL available"
                    })
                    continue
                
                try:
                    slide_result = curriculum_generator.create_module_slide(
                        module_title=module_title,
                        module_content=module_content,
                        image_url=image_url,
                        course_id=course_id,
                        authorization_token=authorization_token
                    )
                    
                    slides_results.append({
                        "module_number": i + 1,
                        "module_title": module_title,
                        "success": True,
                        "result": slide_result
                    })
                    
                    successful_slides += 1
                    logger.info(f"Module slide {i+1} created successfully: {module_title}")
                    
                except Exception as e:
                    logger.error(f"Error creating slide for module {i+1}: {str(e)}")
                    slides_results.append({
                        "module_number": i + 1,
                        "module_title": module_title,
                        "success": False,
                        "error": str(e)
                    })
                    failed_slides += 1
            
            # Prepare final response
            response_data = {
                "success": True,
                "message": "Curriculum generated and Lisa course created successfully",
                "course_creation": {
                    "success": True,
                    "course_title": course_title,
                    "cover_image_url": cover_image_url,
                    "result": course_result
                },
                "module_slides": {
                    "total_modules": len(structured_course["modules"]),
                    "successful_slides": successful_slides,
                    "failed_slides": failed_slides,
                    "results": slides_results
                },
                "structured_course": structured_course,
                "raw_curriculum": curriculum,
                "extracted_text": extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
            }
            
            logger.info("Complete workflow finished successfully")
            return jsonify(response_data)
            
        else:
            return jsonify({"error": "Curriculum generation failed"}), 500
        
    except Exception as e:
        logger.error(f"Error in generate-and-create-lisa-course endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/post-modules-to-course', methods=['POST'])
def post_modules_to_course():
    """Post module slides to an existing Lisa course"""
    try:
        # Get parameters
        course_id = request.form.get('course_id')
        authorization_token = request.form.get('authorization_token')
        
        # Use environment token if not provided
        if not authorization_token and LISA_AUTHORIZATION_TOKEN:
            authorization_token = LISA_AUTHORIZATION_TOKEN
            logger.info("Using authorization token from environment variables")
        elif not authorization_token:
            return jsonify({"error": "No authorization_token provided and no LISA_AUTHORIZATION_TOKEN in environment"}), 400
        
        if not course_id:
            return jsonify({"error": "Missing required field: course_id"}), 400
        
        # Check if PDF file is provided
        if 'pdf_file' not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf_file']
        
        if pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        logger.info(f"Processing PDF: {pdf_file.filename} for course: {course_id}")
        
        # Step 1: Extract text from PDF
        pdf_content = io.BytesIO(pdf_file.read())
        extracted_text = curriculum_generator.extract_text_from_pdf(pdf_content)
        
        if not extracted_text.strip():
            return jsonify({"error": "No text could be extracted from the PDF"}), 400
        
        # Step 2: Generate curriculum
        curriculum = curriculum_generator.generate_curriculum(extracted_text)
        
        if not isinstance(curriculum, dict):
            return jsonify({"error": "Curriculum generation failed"}), 500
        
        # Step 3: Generate images and content for each module
        modules = curriculum.get('modules', [])
        logger.info(f"Generating images for {len(modules)} modules")
        
        slides_results = []
        successful_slides = 0
        failed_slides = 0
        
        for i, module in enumerate(modules):
            logger.info(f"Processing module {i+1}: {module.get('module_title', f'Module {i+1}')}")
            
            module_title = module.get('module_title', f'Module {i+1}')
            module_content = module.get('module_content', '')
            
            # Generate module image
            image_prompt = module.get('module_image_prompt', module.get('module_title', f'Module {i+1}'))
            logger.info(f"Generating image for module {i+1} with prompt: {image_prompt[:100]}...")
            
            try:
                module_image = curriculum_generator.generate_image(image_prompt, include_base64=True)
                
                # Upload module image to S3
                if module_image and "image_url" in module_image:
                    s3_module_url = curriculum_generator.upload_image_to_s3(
                        module_image["image_url"], 
                        module_image["image_id"], 
                        "module"
                    )
                    module_image["s3_url"] = s3_module_url
                    logger.info(f"Module {i+1} image uploaded to S3: {s3_module_url}")
                
                # Use S3 URL if available, otherwise use original URL
                image_url = module_image.get('s3_url') or module_image.get('image_url')
                
                if not image_url:
                    logger.warning(f"No image URL for module {i+1}: {module_title}")
                    failed_slides += 1
                    slides_results.append({
                        "module_number": i + 1,
                        "module_title": module_title,
                        "success": False,
                        "error": "No image URL available"
                    })
                    continue
                
                # Create module slide
                slide_result = curriculum_generator.create_module_slide(
                    module_title=module_title,
                    module_content=module_content,
                    image_url=image_url,
                    course_id=course_id,
                    authorization_token=authorization_token
                )
                
                slides_results.append({
                    "module_number": i + 1,
                    "module_title": module_title,
                    "success": True,
                    "image_url": image_url,
                    "result": slide_result
                })
                
                successful_slides += 1
                logger.info(f"Module slide {i+1} created successfully: {module_title}")
                
            except Exception as e:
                logger.error(f"Error creating slide for module {i+1}: {str(e)}")
                slides_results.append({
                    "module_number": i + 1,
                    "module_title": module_title,
                    "success": False,
                    "error": str(e)
                })
                failed_slides += 1
        
        # Prepare response
        response_data = {
            "success": True,
            "message": f"Module slides posted to course {course_id}",
            "course_id": course_id,
            "module_slides": {
                "total_modules": len(modules),
                "successful_slides": successful_slides,
                "failed_slides": failed_slides,
                "results": slides_results
            }
        }
        
        logger.info(f"Module slides posting completed for course {course_id}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error in post-modules-to-course endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 