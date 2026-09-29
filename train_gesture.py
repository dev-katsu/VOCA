import os
import sys

def main():
    print("==================================================")
    print(" Gesture Detection YOLOv8 Training Script")
    print("==================================================")
    print("Note: If the Roboflow dataset download fails with a BadZipFile error,")
    print("it means the backend export has expired (this is a 2023 dataset).")
    print("To fix this, go to your Roboflow project dashboard and click")
    print("'Generate' to create a new dataset version, or request a fresh export.")
    print("==================================================\n")

    try:
        import roboflow
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "roboflow", "ultralytics"])
        import roboflow

    from roboflow import Roboflow
    rf = Roboflow(api_key="L9Bh022q8AG3kYXWCyqz")
    project = rf.workspace("nathaniel-estabaya").project("teacher")
    
    # Try downloading the dataset
    try:
        dataset = project.version(1).download("yolov8")
        print(f"Dataset downloaded to: {dataset.location}")
    except Exception as e:
        print(f"\n[ERROR] Failed to download dataset from Roboflow: {e}")
        print("Please check your Roboflow dashboard to ensure the yolov8 export is valid/regenerated.")
        return

    # Train the YOLOv8 model using the downloaded dataset
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics package is not installed. Please install it.")
        return

    print("\nStarting YOLOv8 training on the dataset...")
    # Initialize a YOLOv8 nano model (pre-trained)
    model = YOLO("yolov8n.pt") 

    # Train the model
    # Note: dataset.location contains the path to the downloaded dataset.
    # We point data to the data.yaml file inside the dataset folder.
    yaml_path = os.path.join(dataset.location, "data.yaml")
    
    if not os.path.exists(yaml_path):
        print(f"[ERROR] Could not find data.yaml at {yaml_path}")
        return

    model.train(
        data=yaml_path,
        epochs=50,       # Adjust epochs as needed
        imgsz=640,
        batch=16,
        project="runs/detect",
        name="teacher_gesture_model"
    )

    print("\nTraining completed successfully!")
    print("The trained model weights are saved in runs/detect/teacher_gesture_model/weights/")
    print("You can copy best.pt to the 'models' folder and rename it to 'yolov8_custom.pt' to use it in detector.py!")

if __name__ == "__main__":
    main()
