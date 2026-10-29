# FireDtect Models Directory

Place your trained YOLOv8 fire detection weights file here:
`models/fire_yolov8n.pt`

### Supported Models:
- Custom-trained YOLOv8n/s/m models on fire & smoke datasets.
- If `models/fire_yolov8n.pt` is missing, `src/main.py` will fall back to downloading and running standard `yolov8n.pt` to test your camera pipeline and CUDA acceleration setup.
