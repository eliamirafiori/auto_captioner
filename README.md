# Build Image

docker build -t web-captioner .

# Run Container

docker run --rm -it --gpus all -p 7860:7860 web-captioner
