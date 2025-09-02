#!/usr/bin/env python3
"""
Script to create a sample PDF for testing the curriculum generation API
"""

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def create_sample_pdf():
    """Create a sample PDF with curriculum content"""
    
    # Create the PDF document
    doc = SimpleDocTemplate("sample_curriculum.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        spaceBefore=20
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6
    )
    
    # Read the sample content
    with open('sample_content.txt', 'r') as f:
        content = f.read()
    
    # Split content into sections
    sections = content.split('\n\n')
    
    # Build the story (content)
    story = []
    
    for section in sections:
        if section.strip():
            lines = section.strip().split('\n')
            title = lines[0].strip()
            
            if title == "Introduction to Machine Learning":
                # Main title
                story.append(Paragraph(title, title_style))
            elif title.endswith(':') and len(lines) > 1:
                # Section heading
                story.append(Paragraph(title, heading_style))
                
                # Add content
                for line in lines[1:]:
                    if line.strip():
                        if line.startswith('- '):
                            # Bullet point
                            story.append(Paragraph(f"• {line[2:]}", normal_style))
                        elif line.startswith('Module '):
                            # Module heading
                            story.append(Paragraph(line, heading_style))
                        else:
                            # Regular text
                            story.append(Paragraph(line, normal_style))
            else:
                # Regular paragraph
                story.append(Paragraph(title, normal_style))
    
    # Build the PDF
    doc.build(story)
    print("✅ Sample PDF created: sample_curriculum.pdf")
    print("📄 You can now use this PDF to test the curriculum generation API")

if __name__ == "__main__":
    create_sample_pdf() 