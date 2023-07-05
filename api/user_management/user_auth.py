from fastapi.routing import APIRouter
from fastapi.param_functions import Depends
from fastapi import Depends, FastAPI, HTTPException, status, Request, Response
from jose import jwt
from starlette.responses import RedirectResponse

from api.user_management.dtos.change_password_dto import ChangePasswordDTO
from api.user_management.dtos.login_user_dto import LoginUserDTO
from config import default_log
from data.dbapi.user_dbapi import read_queries, write_queries
from data.dbapi.user_dbapi.dtos.update_user_dto import UpdateUserDTO
from data.dbapi.user_dbapi.write_queries import update_user
from data.models.users import Users
from decorators.handle_generic_exception import frontend_api_generic_exception
from logic.auth.password_reset_utilities import send_reset_password_email, \
    validate_email_token, get_email_from_reset_password_request
from logic.auth.redis_token_cache import RedisTokenCache
from logic.auth.token_cache import TokenCache
from logic.auth.token_management import authenticate_user, create_access_token, \
    get_user_from_token, oauth2_scheme
import config



auth_router = APIRouter( tags=['auth'])

#TODO: Use FastAPI-Users library
@auth_router.get('/login')
@frontend_api_generic_exception
def login(login_user: LoginUserDTO):
    if(login_user.email == "" or login_user.password  == ""):
        return dict(error="Error: enter mail id and password", response="error"), 401

    user,msg = authenticate_user(login_user.email, login_user.password)

    if not user:
        return dict(error=msg, response="error: User not found")

        # raise HTTPException(
        #     status_code=status.HTTP_401_UNAUTHORIZED,
        #     detail=msg ,
        #     headers={"WWW-Authenticate": "Bearer"},
        # )

    access_token = create_access_token(email=user.email)
    return dict(token=access_token),200
    # return {"Hello World"}



@auth_router.get('/logout')
@frontend_api_generic_exception
def logout(token: str = Depends(oauth2_scheme)):
    token_cache = RedisTokenCache()
    payload = jwt.decode(token, config.secret_key, algorithms=['HS256'])
    email = payload.get('sub')
    iat = payload.get('iat')

    token_cache.delete_tokens_for_user(email + "_" + str(iat))

    return dict(response="ok")


@auth_router.get('/set-new-password/{token}')
@frontend_api_generic_exception
def reset_password(token):

    return dict(token=token)


@auth_router.post('/set-new-password')
@frontend_api_generic_exception
def change_password(dto: ChangePasswordDTO):

    token = dto.token
    user = get_user_from_token(token)
    user_id = user.id

    default_log.debug(f"Resetting password for {user.email}")

    if dto.password1 == dto.password2:
        new_user_dto = UpdateUserDTO(email=user.email,
                                     password=dto.password1,
                                     is_verified=True)

        write_queries.update_user(new_user_dto)


    return dict(response="ok")


@auth_router.get('/reset-password-request')
@frontend_api_generic_exception
def reset_password_request(email):
    send_reset_password_email(email)
    return dict(response="ok")


@auth_router.get('/process-reset-password-request')
@frontend_api_generic_exception
def process_reset_password_request(email_token, hashed_one_time_password):
    email = get_email_from_reset_password_request(email_token,
                                                  hashed_one_time_password)
    if email:
        default_log.debug(f"Email found: {email}")
        new_jwt_token = create_access_token(email)

        return RedirectResponse(f"{config.frontend_url}/set-new-password?new_jwt_token={new_jwt_token}")
    else:
        # default_log.log("Email not found.")
        raise Exception("email token is invalid")

    return dict(response="ok")


@auth_router.get('/verify-new-user')
def verify_new_user(email_token):
    email = validate_email_token(email_token)

    if email:
        update_dto = UpdateUserDTO(email=email, is_verified=True)
        user_id = update_user(update_dto)
        return RedirectResponse(f"{config.frontend_url}/login")
    else:
        return Response(status_code=404)
