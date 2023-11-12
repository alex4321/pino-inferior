# Use the latest MiniConda3 image as base
FROM continuumio/miniconda3:latest

# Set the working directory in the container to /app
WORKDIR /app

# Install gcc
RUN apt update
RUN apt install -y gcc

# Update python
RUN conda install python=3.11.5

# Copy the current directory contents into the container at /app
COPY migration /app
COPY pino_inferior /app
COPY alembic.ini /app
COPY settings.ini /app
COPY setup.py /app
COPY README.md /app

# Install the Python package in editable mode with dependencies
RUN python3 setup.py develop

# Run Alembic migrations
RUN python3 -m alembic upgrade head

# Expose port 8766 for websockets
EXPOSE 8766

# Run the pino_inferior server on container startup
CMD ["python3", "-m", "pino_inferior.server"]
