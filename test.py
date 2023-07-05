import base64
from fastapi import FastAPI, Request, File, UploadFile,Form
from fastapi.responses import HTMLResponse
import psycopg2
from fastapi.applications import RequestValidationError
from typing import List
from standard_responses.standard_json_response import standard_json_response
import boto3
from fastapi.templating import Jinja2Templates
import io
from PIL import Image
from starlette.staticfiles import StaticFiles

app = FastAPI()

# Database connection settings
DB_HOST = "localhost"
DB_NAME = "your_new_database"
DB_USER = "postgres"
DB_PASS = "password"

@app.exception_handler(RequestValidationError)
async def default_exception_handler(request: Request, exc: RequestValidationError):
    return standard_json_response(
        status_code=200,
        data={},
        error=True,
        message=str(exc)
    )

templates=Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


# HTML form endpoint
@app.get("/")
def home(request: Request):
    face_detected=None
    return templates.TemplateResponse("index.html", {"request": request,"face_detected":face_detected})

def recognizeFace(client,image_data):
    face_matched = False
    res=client.search_faces_by_image(CollectionId="missingpersons",Image={"Bytes":image_data},MaxFaces=1,FaceMatchThreshold=85)
    if (not res['FaceMatches']):
        face_matched = False
    else:
        face_matched = True
        

    return face_matched, res 

@app.post("/submit")
async def submit_details(request: Request,file: List[UploadFile] = File(...)):
    image_data = await file[0].read()  # Await the coroutine to get the image bytes
    
    client = boto3.client('rekognition', region_name='us-east-1')

    face_detected,res=recognizeFace(client,image_data)
    
    # print(res['FaceMatches'][0]['Face']['FaceId'])
    if not face_detected :
        # print("not detect")
        response = client.index_faces(
            Image={"Bytes": image_data},
            CollectionId='missingpersons',
            DetectionAttributes=['ALL']
        )  

        _,new_res=recognizeFace(client,image_data)

        face_id=new_res['FaceMatches'][0]['Face']['FaceId']
        # face_id=0
        image_data = base64.b64encode(image_data).decode("utf-8")
        # face_detected=False
        # print(face_detected)
        return templates.TemplateResponse("index.html", {"request":request,"face_detected": face_detected,"face_id":face_id,"image_data":image_data})
    else:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
        cursor = conn.cursor()
        face_id=res['FaceMatches'][0]['Face']['FaceId']
        select_query = '''SELECT * FROM missing_persons_info WHERE face_id = %s'''
        cursor.execute(select_query, (face_id,))
        record = cursor.fetchone()

        cursor.close()
        conn.close()   
        if record:
            columns = ['face_id', 'name', 'age', 'address', 'contact_info']
            record_dict = dict(zip(columns, record))
            return templates.TemplateResponse("index.html",{"request":request,"face_detected":face_detected,"record_dict": record_dict})
        else:
            return {"message": "Record not found"}    
        # return templates.TemplateResponse("index.html", {"request":request,"face_detected": face_detected})

# DB_HOST = "localhost"
# DB_NAME = "your_new_database"
# DB_USER = "postgres"
# DB_PASS = "password"

@app.post("/insertdata")
async def submit_details(name: str = Form(...), age: int = Form(...), address: str = Form(...),face_id: str =Form(...),contact: str =Form(...)):
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
    cursor = conn.cursor()
    # client = boto3.client('rekognition', region_name='us-east-1')  
    try:
        cursor.execute("INSERT INTO missing_persons_info (face_id,name, age, address,contact) VALUES (%s, %s, %s, %s, %s)", (face_id,name, age, address,contact))
        conn.commit()
        # image_data = base64.b64decode(image_data)

        # response = client.index_faces(
        #     Image={"Bytes": image_data},
        #     CollectionId='missingpersons',
        #     DetectionAttributes=['ALL']
        # )    
        return {"message": "User details submitted successfully"}
    except Exception as e:
        return {"message": "Error occurred during form submission", "error": str(e)}
           
    finally:
        cursor.close()
        conn.close()
        
   

