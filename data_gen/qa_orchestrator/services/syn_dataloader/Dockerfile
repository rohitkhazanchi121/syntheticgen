FROM python:3.13

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy the project files
COPY pyproject.toml /app/

# Install dependencies using Poetry
RUN poetry install --no-root

# Copy the rest of the application files
COPY . /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["poetry", "run", "python", "dataloader.py"]
