# Use x86_64 Amazon Linux 2 base image
FROM --platform=linux/amd64 amazonlinux:2 AS builder

# Install system dependencies and graphviz
RUN yum update -y && \
    yum install -y \
    python3-pip \
    python3-devel \
    graphviz \
    graphviz-devel \
    gcc \
    gcc-c++ \
    make && \
    yum clean all && \
    rm -rf /var/cache/yum

# Create necessary directories
RUN mkdir -p /opt/python && \
    mkdir -p /opt/bin && \
    mkdir -p /opt/lib && \
    mkdir -p /opt/lib/graphviz

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt -t /opt/python/

# Copy dot binary and its dependencies
RUN cp /usr/bin/dot /opt/bin/ && \
    cp -r /usr/lib64/graphviz/* /opt/lib/graphviz/

# Copy all shared library dependencies
RUN for lib in $(ldd /usr/bin/dot | grep "=> /" | awk '{print $3}'); do \
    cp -v "$lib" /opt/lib/; \
    done && \
    for lib in /usr/lib64/graphviz/*.so*; do \
        if [ -f "$lib" ]; then \
            for dep in $(ldd "$lib" 2>/dev/null | grep "=> /" | awk '{print $3}'); do \
                cp -v "$dep" /opt/lib/ 2>/dev/null || true; \
            done; \
        fi; \
    done

# Create config6 file
RUN cd /opt/lib/graphviz && \
    echo "$(pwd)/libgvplugin_core.so.6" > config6 && \
    echo "$(pwd)/libgvplugin_dot_layout.so.6" >> config6 && \
    echo "$(pwd)/libgvplugin_gd.so.6" >> config6 && \
    echo "$(pwd)/libgvplugin_neato_layout.so.6" >> config6 && \
    echo "$(pwd)/libgvplugin_pango.so.6" >> config6

# Set permissions
RUN chmod 755 /opt/bin/dot && \
    chmod -R 755 /opt/lib

# Run dot -c in the context of the layer
RUN LD_LIBRARY_PATH=/opt/lib:/opt/lib/graphviz \
    PATH=/opt/bin:$PATH \
    /opt/bin/dot -c
