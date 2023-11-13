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
COPY migration /app/migration
COPY pino_inferior /app/pino_inferior
COPY alembic.ini /app/alembic.ini
COPY settings.ini /app/settings.ini
COPY setup.py /app/setup.py
COPY README.md /app/README.md
COPY .env.deploy /app/.env.deploy

# Install the Python package in editable mode with dependencies
# Avoid version breaking by installing aiohttp before everything
RUN python3 -m pip install aiohttp
RUN python3 setup.py develop

# Run Alembic migrations
RUN bash -c "sed '/^$/d; s/^/export /' .env.deploy > .env.deploy.sh"
RUN bash -c "source .env.deploy.sh; python3 -m alembic upgrade head"

# Expose port 8766 for websockets
EXPOSE 8766

# Run the pino_inferior server on container startup
CMD ["python3", "-m", "pino_inferior.server"]
