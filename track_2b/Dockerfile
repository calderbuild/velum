# Velum needs nothing beyond the Python standard library, so the image is the base image plus our code and data.
FROM python:3.12-slim
WORKDIR /app
COPY src/ src/
COPY data/ data/
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home velum && mkdir out && chown velum out
USER velum
EXPOSE 8000
# Anonymise the bundled decisions, print the results, then open the review interface on port 8000.
CMD ["sh", "-c", "python -m velum demo && exec python -m velum serve --host 0.0.0.0"]
