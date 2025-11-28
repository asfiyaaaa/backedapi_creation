from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
from typing import Optional, List
import os

app = FastAPI(title="Monitoring Tool API")

# -------------------------------------------------------
# DATABASE CONNECTION  (MYSQL)
# -------------------------------------------------------
DB_USER = "cogninode"
DB_PASS = "19801980"
DB_HOST = "16.112.102.135"
DB_NAME = "monitor"

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# -------------------------------------------------------
# DATABASE MODELS (SQLAlchemy)
# -------------------------------------------------------

class Employee(Base):
    __tablename__ = "employees"

    emp_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100))
    email = Column(String(120), unique=True)
    phone = Column(String(15))
    gender = Column(SAEnum("Male", "Female", "Other", "Prefer not to say"))
    blood_group = Column(SAEnum("A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"))
    password_hash = Column(String(255))
    department = Column(String(100))
    designation = Column(String(100))
    join_date = Column(Date)
    status = Column(SAEnum("active", "inactive", "terminated", "onleave"))
    created_at = Column(DateTime, default=datetime.now)

    logins = relationship("LoginActivity", back_populates="employee")
    leaves = relationship("Leave", back_populates="employee")
    tasks = relationship("Task", back_populates="employee")


class LoginActivity(Base):
    __tablename__ = "login_activity"

    activity_id = Column(Integer, primary_key=True, autoincrement=True)
    emp_id = Column(Integer, ForeignKey("employees.emp_id", ondelete="CASCADE"))
    login_date = Column(Date)
    login_time = Column(DateTime)
    logout_time = Column(DateTime, nullable=True)
    ip_address = Column(String(50))
    device_info = Column(String(255))

    employee = relationship("Employee", back_populates="logins")


class Leave(Base):
    __tablename__ = "leaves"

    leave_id = Column(Integer, primary_key=True, autoincrement=True)
    emp_id = Column(Integer, ForeignKey("employees.emp_id", ondelete="CASCADE"))
    leave_type = Column(SAEnum("Casual", "Sick", "Earned", "Unpaid"))
    start_date = Column(Date)
    end_date = Column(Date)
    reason = Column(Text)
    status = Column(SAEnum("pending", "approved", "rejected"), default="pending")
    admin_comment = Column(Text)
    applied_at = Column(DateTime, default=datetime.now)
    responded_at = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="leaves")


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    emp_id = Column(Integer, ForeignKey("employees.emp_id", ondelete="CASCADE"))
    title = Column(String(200))
    description = Column(Text)
    status = Column(SAEnum("in_progress", "review", "done"))
    assigned_by = Column(String(100))
    assigned_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    employee = relationship("Employee", back_populates="tasks")





# -------------------------------------------------------
# Pydantic Schemas
# -------------------------------------------------------

class EmployeeCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str]
    gender: Optional[str] = "Prefer not to say"
    blood_group: Optional[str]
    password_hash: str
    department: Optional[str]
    designation: Optional[str]
    join_date: Optional[datetime]
    status: Optional[str] = "active"


class LoginRequest(BaseModel):
    emp_id: int
    ip_address: str
    device_info: str


class LeaveCreate(BaseModel):
    emp_id: int
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str]


class TaskCreate(BaseModel):
    emp_id: int
    title: str
    description: Optional[str]
    assigned_by: str


class TaskUpdate(BaseModel):
    status: str


# -------------------------------------------------------
# Dependency
# -------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------
# EMPLOYEE APIs
# -------------------------------------------------------

@app.post("/employees")
def create_employee(data: EmployeeCreate, db=Depends(get_db)):
    exists = db.query(Employee).filter(Employee.email == data.email).first()
    if exists:
        raise HTTPException(status_code=400, detail="Email already exists")

    emp = Employee(**data.dict())
    db.add(emp)
    db.commit()
    db.refresh(emp)

    return {"message": "Employee created", "employee_id": emp.emp_id}


@app.get("/employees")
def list_employees(db=Depends(get_db)):
    return db.query(Employee).all()


# -------------------------------------------------------
# LOGIN / LOGOUT APIs
# -------------------------------------------------------

@app.post("/login")
def login_employee(login: LoginRequest, db=Depends(get_db)):
    now = datetime.now()

    record = LoginActivity(
        emp_id=login.emp_id,
        login_date=now.date(),
        login_time=now,
        ip_address=login.ip_address,
        device_info=login.device_info
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "message": "Login successful",
        "activity_id": record.activity_id,
        "login_time": record.login_time
    }


@app.post("/logout/{activity_id}")
def logout(activity_id: int, db=Depends(get_db)):
    record = db.query(LoginActivity).filter(LoginActivity.activity_id == activity_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Login activity not found")

    record.logout_time = datetime.now()
    db.commit()

    return {"message": "Logout updated"}


# -------------------------------------------------------
# LEAVE APIs
# -------------------------------------------------------

@app.post("/leave")
def apply_leave(data: LeaveCreate, db=Depends(get_db)):
    leave = Leave(
        emp_id=data.emp_id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status="pending"
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    return {"message": "Leave applied", "leave_id": leave.leave_id}


@app.get("/leaves/{emp_id}")
def get_leaves(emp_id: int, db=Depends(get_db)):
    return db.query(Leave).filter(Leave.emp_id == emp_id).all()


@app.put("/leave/response/{leave_id}")
def respond_leave(leave_id: int, status: str, admin_comment: str = "", db=Depends(get_db)):
    leave = db.query(Leave).filter(Leave.leave_id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    leave.status = status
    leave.admin_comment = admin_comment
    leave.responded_at = datetime.now()

    db.commit()
    return {"message": f"Leave {status}"}


# -------------------------------------------------------
# TASK APIs
# -------------------------------------------------------

@app.post("/admin/task")
def assign_task(data: TaskCreate, db=Depends(get_db)):
    task = Task(
        emp_id=data.emp_id,
        title=data.title,
        description=data.description,
        assigned_by=data.assigned_by,
        status="in_progress"
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return {"message": "Task assigned", "task_id": task.task_id}


@app.post("/task/update/{task_id}")
def update_task(task_id: int, data: TaskUpdate, db=Depends(get_db)):
    task = db.query(Task).filter(Task.task_id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = data.status
    task.updated_at = datetime.now()
    db.commit()

    return {"message": "Task updated"}


@app.get("/admin/tasks/{emp_id}")
def get_tasks(emp_id: int, db=Depends(get_db)):
    return db.query(Task).filter(Task.emp_id == emp_id).all()


# -------------------------------------------------------
# ROOT
# -------------------------------------------------------

@app.get("/")
def home():
    return {"message": "Monitoring Tool API is running!"}
