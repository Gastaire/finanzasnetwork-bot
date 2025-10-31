from sqlalchemy.orm import Session
from . import models, schemas, security

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    # Obtenemos el hash del password
    hashed_password = security.get_password_hash(user.password)
    
    # Creamos el objeto User del modelo de BBDD
    db_user = models.User(
        email=user.email, 
        hashed_password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user