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
from fastapi.responses import Response
from starlette.middleware.cors import CORSMiddleware
from api.test.healthcheck import router as test_router
from api.user_management.user_auth import auth_router
from api.user_management.user_basic_api import user_router
import uvicorn
import config
import bcrypt
import binascii

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:4200",
    "http://localhost:3000"  # React
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(test_router)
app.include_router(user_router)
app.include_router(auth_router)


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

img_data=None
faceId=None
# HTML form endpoint




@app.get("/")
def home(request: Request):
    face_detected=None
    matched=None
    auth=None
    return templates.TemplateResponse("index.html", {"request": request,"face_detected":face_detected,"matched":matched,"auth":auth})

def recognizeFace(client,image_data):
    face_matched = False
    res=client.search_faces_by_image(CollectionId="missingpersons",Image={"Bytes":image_data},MaxFaces=1,FaceMatchThreshold=85)
    if (not res['FaceMatches']):
        face_matched = False
    else:
        face_matched = True
        
    return face_matched, res 


@app.post("/signup")
async def signup_details(request: Request,name: str = Form(...),number: str = Form(...),password:str = Form(...)):
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
    cursor = conn.cursor()
    password=binascii.hexlify(password.encode()).decode()
   
    cursor.execute("INSERT INTO users (name,phone,password) VALUES (%s, %s, %s)", (name, number,password))
    conn.commit()
    cursor.close()
    conn.close()
    auth=True
    face_detected=None
    return templates.TemplateResponse("index.html", {"request":request,"face_detected":face_detected,"auth":auth})

# def text_to_binary(text):
#     binary = ''
#     for char in text:
#         binary += bin(ord(char))[2:].zfill(8)  # Convert character to binary and pad with zeros
#     return binary

@app.post("/signin")
async def signin_details(request: Request,number:str=Form(...),password:str=Form(...)):
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
    cursor = conn.cursor()
    cursor.execute('''SELECT password FROM users where phone = %s''',(number,))
    record=cursor.fetchone()[0]
    # print()
    cursor.close()
    conn.close()
    if(record == binascii.hexlify(password.encode()).decode()):
        matched=1
        auth=True
        face_detected=None
        return templates.TemplateResponse("index.html", {"request":request,"face_detected":face_detected,"auth":auth})
    else:
        matched=0
        return {"matched":matched}
    
    



@app.post("/submit")
async def submit_details(request: Request,file: List[UploadFile] = File(...)):
    image_data = await file[0].read()  # Await the coroutine to get the image bytes
    
    client = boto3.client('rekognition', region_name='us-east-1')

    face_detected,res=recognizeFace(client,image_data)
    

    if not face_detected :

        global img_data
        img_data=image_data
        auth=True
        return templates.TemplateResponse("index.html", {"request":request,"face_detected": face_detected,"auth":auth})
    else:
        global faceId
        # faceId=face_id

        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
        cursor = conn.cursor()
        face_id=res['FaceMatches'][0]['Face']['FaceId']
        faceId=face_id
        select_query = '''SELECT * FROM missing_persons_info WHERE face_id = %s'''
        cursor.execute(select_query, (face_id,))
        record = cursor.fetchone()

        cursor.close()
        conn.close()   
        if record:
            columns = ['face_id', 'name', 'age', 'address', 'contact_info']
            record_dict = dict(zip(columns, record))
            auth=True
            return templates.TemplateResponse("index.html",{"request":request,"face_detected":face_detected,"auth":auth,"record_dict": record_dict})
        else:
            return {"message": "Record not found"}    

@app.post("/insertdata")
async def submit_details(name: str = Form(...), age: int = Form(...), address: str = Form(...),contact: str =Form(...)):
    # print('Hello')
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
    cursor = conn.cursor()
    client = boto3.client('rekognition', region_name='us-east-1') 
    global img_data

    try:
        response = client.index_faces(
            Image={"Bytes": img_data},
            CollectionId='missingpersons',
            DetectionAttributes=['ALL']
        )  

        _,new_res=recognizeFace(client,img_data)

        face_id=new_res['FaceMatches'][0]['Face']['FaceId']

        cursor.execute("INSERT INTO missing_persons_info (face_id,name, age, address,contact) VALUES (%s, %s, %s, %s, %s)", (face_id,name, age, address,contact))
        conn.commit()
        return Response(status_code=204)
    except Exception as e:
        return {"message": "Error occurred during form submission", "error": str(e)}
           
    finally:
        cursor.close()
        conn.close()




@app.post("/insertrecieverdata")
async def submit_reciever_details(name: str = Form(...),contact: str = Form(...)):
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
    cursor = conn.cursor()

    global faceId

    try:


        cursor.execute("UPDATE missing_persons_info SET reciever_name = %s, reciever_contact = %s WHERE face_id = %s", (name, contact, faceId))

        conn.commit()
        # return {"message": "User details submitted successfully"}
        return Response(status_code=204)
    except Exception as e:
        return {"message": "Error occurred during form submission", "error": str(e)}
           
    finally:
        cursor.close()
        conn.close()

        
   
def create_app():
    return app


# if __name__ == '__main__':
#     app = create_app()
#     uvicorn.run('main:app',
#                 host=config.fastapi_host, port=config.fastapi_port,
#                 reload=config.reload)

