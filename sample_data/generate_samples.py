import os
from pathlib import Path
import docx
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

SAMPLE_DIR = Path(__file__).resolve().parent

def create_sample_docx():
    """Create sample DOCX resume for Alex Morgan (Senior Full Stack Engineer)."""
    docx_path = SAMPLE_DIR / "sample_resume_fullstack.docx"
    doc = docx.Document()
    
    # Title / Name
    title_p = doc.add_paragraph()
    run = title_p.add_run("Alex Morgan")
    run.bold = True
    run.font.size = docx.shared.Pt(22)
    
    # Contact Info
    contact_p = doc.add_paragraph("San Francisco, CA | alex.morgan.dev@gmail.com | (415) 555-0192 | linkedin.com/in/alexmorgan-dev | github.com/alexmorgan")
    contact_p.paragraph_format.space_after = docx.shared.Pt(12)
    
    # Summary
    doc.add_heading("Professional Summary", level=1)
    doc.add_paragraph(
        "Results-oriented Senior Full Stack Engineer with 6+ years of experience designing and scaling "
        "distributed cloud applications. Proven track record in Python (FastAPI/Django), TypeScript, React, "
        "microservices, and PostgreSQL. Experienced in Docker containerization, Kubernetes orchestration, and CI/CD automation."
    )
    
    # Technical Skills
    doc.add_heading("Technical Skills", level=1)
    doc.add_paragraph("Programming Languages: Python, TypeScript, JavaScript, SQL, Go, HTML, CSS")
    doc.add_paragraph("Frameworks & Libraries: React, Next.js, FastAPI, Django, Node.js, Express, Redux, Tailwind CSS")
    doc.add_paragraph("Cloud & DevOps: AWS, Docker, Kubernetes, Terraform, CI/CD, GitHub Actions, Linux")
    doc.add_paragraph("Databases & Tools: PostgreSQL, Redis, MongoDB, GraphQL, REST APIs, Git, Jira, Agile")
    
    # Experience
    doc.add_heading("Work Experience", level=1)
    
    exp1_title = doc.add_paragraph()
    exp1_title.add_run("Senior Full Stack Software Engineer | TechNova Solutions").bold = True
    exp1_title.add_run(" (2022 - Present)")
    doc.add_paragraph("• Architected and developed high-throughput microservices using Python (FastAPI) and PostgreSQL, handling 15M+ daily requests.")
    doc.add_paragraph("• Built responsive, modern customer-facing web applications using React, TypeScript, and Next.js, decreasing page load latency by 35%.")
    doc.add_paragraph("• Containerized legacy workloads using Docker and deployed onto AWS EKS (Kubernetes) with automated CI/CD via GitHub Actions.")
    doc.add_paragraph("• Mentored junior engineers, led code reviews, and championed unit testing and TDD best practices.")
    
    exp2_title = doc.add_paragraph()
    exp2_title.add_run("Full Stack Software Engineer | CloudScale Systems").bold = True
    exp2_title.add_run(" (2019 - 2022)")
    doc.add_paragraph("• Developed REST and GraphQL APIs using Python (Django) and Node.js for B2B financial analytics dashboard.")
    doc.add_paragraph("• Implemented Redis caching layer reducing database query overhead by 45%.")
    doc.add_paragraph("• Collaborated with product managers and designers in Agile/Scrum sprints to deliver features on time.")
    
    # Education
    doc.add_heading("Education", level=1)
    doc.add_paragraph("Bachelor of Science in Computer Science | University of California, Berkeley (2015 - 2019)")
    
    # Certifications
    doc.add_heading("Certifications", level=1)
    doc.add_paragraph("• AWS Certified Solutions Architect - Associate")
    doc.add_paragraph("• Certified Kubernetes Administrator (CKA)")
    
    doc.save(docx_path)
    print(f"Created {docx_path}")

def create_sample_pdf():
    """Create sample PDF resume for Priya Sharma (AI / Machine Learning Engineer)."""
    pdf_path = SAMPLE_DIR / "sample_resume_ai_engineer.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('NameTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor("#1e293b"))
    subtitle_style = ParagraphStyle('ContactSub', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#475569"))
    section_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor("#0f766e"), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9.5, leading=13, textColor=colors.HexColor("#1e293b"))
    bullet_style = ParagraphStyle('Bullet', parent=body_style, leftIndent=12, bulletIndent=4)
    
    story = []
    
    story.append(Paragraph("<b>Priya Sharma</b>", title_style))
    story.append(Paragraph("New York, NY | priya.sharma.ml@gmail.com | (212) 555-0144 | linkedin.com/in/priyasharma-ai | github.com/priyasharma-ml", subtitle_style))
    story.append(Spacer(1, 8))
    
    story.append(Paragraph("<b>Professional Summary</b>", section_style))
    story.append(Paragraph("Machine Learning Engineer with 4+ years of experience specializing in Generative AI, Large Language Models (LLMs), RAG pipelines, and PyTorch. Proven ability to take research models into high-availability production environments using FastAPI, Docker, and AWS.", body_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>Technical Skills</b>", section_style))
    story.append(Paragraph("<b>Languages & Frameworks:</b> Python, PyTorch, TensorFlow, Scikit-Learn, FastAPI, LangChain, LlamaIndex, HuggingFace", body_style))
    story.append(Paragraph("<b>Core Competencies:</b> Large Language Models (LLMs), RAG, NLP, Computer Vision, Transformers, Vector Search, Fine-Tuning", body_style))
    story.append(Paragraph("<b>Cloud & Infrastructure:</b> AWS, Docker, Kubernetes, Linux, Git, CI/CD, Redis, PostgreSQL, Pinecone, Milvus", body_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>Professional Experience</b>", section_style))
    story.append(Paragraph("<b>AI Systems Engineer | Apex AI Labs</b> (2022 - Present)", body_style))
    story.append(Paragraph("• Built low-latency Retrieval-Augmented Generation (RAG) pipelines using LangChain, Qdrant vector database, and FastAPI serving over 500k queries/day.", bullet_style))
    story.append(Paragraph("• Fine-tuned open-source LLMs (Llama 3, Mistral) for domain-specific medical document summarization, achieving 92% factual accuracy.", bullet_style))
    story.append(Paragraph("• Deployed model inference endpoints on AWS SageMaker with Docker containerization and auto-scaling.", bullet_style))
    story.append(Spacer(1, 4))
    
    story.append(Paragraph("<b>Machine Learning Engineer | DataCore Analytics</b> (2020 - 2022)", body_style))
    story.append(Paragraph("• Developed NLP classification and sentiment models using PyTorch, HuggingFace Transformers, and Scikit-Learn.", bullet_style))
    story.append(Paragraph("• Automated training and evaluation workflows using Python, Pandas, and GitHub Actions CI/CD.", bullet_style))
    story.append(Paragraph("• Partnered with cross-functional teams to deploy real-time analytics features.", bullet_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>Education</b>", section_style))
    story.append(Paragraph("Master of Science in Data Science | Columbia University (2018 - 2020)", body_style))
    story.append(Paragraph("Bachelor of Technology in Computer Science | Delhi Technological University (2014 - 2018)", body_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph("<b>Certifications</b>", section_style))
    story.append(Paragraph("• AWS Certified Machine Learning - Specialty", bullet_style))
    story.append(Paragraph("• Deep Learning Specialization (DeepLearning.AI)", bullet_style))
    
    doc.build(story)
    print(f"Created {pdf_path}")

if __name__ == "__main__":
    create_sample_docx()
    create_sample_pdf()
