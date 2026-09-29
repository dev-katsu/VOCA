import os
from ultralytics import YOLO

def main():
    yaml_path = os.path.abspath("teacher_dataset/data.yaml")
    
    if not os.path.exists(yaml_path):
        print(f"[ERROR] Could not find data.yaml at {yaml_path}")
        return

    print("Starting YOLOv8 training on the dataset...")
    
    # Initialize a YOLOv8 nano model
    model = YOLO("yolov8n.pt") 

    # We use CPU since AMD Radeon natively requires ROCm (Linux/WSL2) 
    # or torch-directml (which is not available for Python 3.14).
    model.train(
        data=yaml_path,
        epochs=30,      # 30 epochs for a quick train on CPU
        imgsz=640,
        batch=8,
        device='cpu', 
        project="runs/detect",
        name="teacher_gesture_model"
    )

    print("\nTraining completed successfully!")
    print("Copying the best weights to models/yolov8_custom.pt...")
    
    import shutil
    best_weights = "runs/detect/teacher_gesture_model/weights/best.pt"
    if os.path.exists(best_weights):
        shutil.copy(best_weights, "models/yolov8_custom.pt")
        print("Done! detector.py will now automatically use the custom model.")

if __name__ == "__main__":
    main()
