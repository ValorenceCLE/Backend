# **FastAPI Backend for Raspberry Pi Project**

This repository contains the backend server built with FastAPI for the Raspberry Pi project, aimed at replacing the Control By Web (CBW) system with a custom circuit board powered by an embedded Raspberry Pi.

_[Control By Web](https://controlbyweb.com/)_

## **Background**

- The CBW system provides remote relay control, real-time sensor readings, and a web interface for monitoring and managing hardware.
- This project aims to develop a modern, efficient backend using **FastAPI** to replace the CBW’s backend functionalities.
- In addition to matching CBW's capabilities, this backend is designed for improved performance, better data handling, and enhanced integration with frontend services.

## **Project Features**

- **Real-Time Monitoring**: Provide live sensor data collected by the Raspberry Pi.
- **Relay Control**: Manage relays through API endpoints.
- **Data Management**: Store and retrieve sensor data efficiently.
- **Secure Access**: User authentication and role-based access control.

## **Project Installation**

1. Clone the repository:  
    **`git clone https://github.com/ValorenceCLE/Backend.git`**

2. Navigate to the project directory:  
    **`cd Backend`**

3. Create and activate a virtual environment:  
    **`python -m venv venv`**  
    **`source venv/bin/activate`** (Linux/macOS)  
    **`venv\Scripts\activate`** (Windows)

4. Install the required dependencies:  
    **`pip install -r requirements.txt`**

5. Start the FastAPI server:  
    **`uvicorn main:app --reload`**

6. Open your browser and navigate to **`http://localhost:8000`** to view the API documentation.

## **Project Configuration**

- The backend is configured to communicate with frontend services hosted on the Raspberry Pi.

## **Technologies Used**

- **FastAPI**: The core framework for building the backend.
- **SQLAlchemy**: For database interactions.
- **Pydantic**: For data validation.
- **Uvicorn**: ASGI server for serving FastAPI applications.

## **Acknowledgment**

All code was written and developed by **Landon Bell**, an employee of **Valorence**.

All Hardware was developed by **Kelton Page**, an employee of **Valorence**.

