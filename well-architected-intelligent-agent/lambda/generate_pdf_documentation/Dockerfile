FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies for WeasyPrint
RUN yum update -y && \
    yum install -y \
    pango \
    pango-devel \
    libffi-devel \
    cairo \
    cairo-devel \
    gcc \
    gdk-pixbuf2 \
    gdk-pixbuf2-devel \
    libxml2-devel \
    libxslt-devel \
    ghostscript \
    && yum clean all

# Install fonts
RUN yum install -y \
    urw-fonts \
    freetype \
    freetype-devel \
    fontconfig \
    fontconfig-devel

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install Python dependencies
RUN pip install -r requirements.txt

# Copy application code
COPY app.py ${LAMBDA_TASK_ROOT}

# Set the handler
CMD ["app.lambda_handler"]