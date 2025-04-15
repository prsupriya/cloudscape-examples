FROM public.ecr.aws/lambda/python:3.9

# Install Graphviz and its dependencies
RUN yum update -y && \
    yum install -y graphviz graphviz-devel && \
    yum clean all

# Create necessary directories
RUN mkdir -p /opt/python && mkdir -p /opt/bin

# Copy Graphviz binaries to the layer
RUN cp /usr/bin/dot /opt/bin/ && \
    cp -r /usr/lib64/graphviz* /opt/lib/ && \
    cp /usr/lib64/libgvc.so* /opt/lib/ && \
    cp /usr/lib64/libcgraph.so* /opt/lib/ && \
    cp /usr/lib64/libpathplan.so* /opt/lib/ && \
    cp /usr/lib64/libxdot.so* /opt/lib/ && \
    cp /usr/lib64/libcdt.so* /opt/lib/

# Copy requirements.txt
COPY python/requirements.txt .

# Install Python dependencies
RUN pip install -r requirements.txt -t /opt/python/
