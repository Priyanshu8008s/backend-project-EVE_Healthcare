import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    bookings = relationship("Booking", back_populates="user")

class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) 
    location = Column(String, nullable=False) 
    
    tests = relationship("DiagnosticTest", back_populates="centre", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="centre")

class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"
    
    id = Column(Integer, primary_key=True, index=True)
    centre_id = Column(Integer, ForeignKey("diagnostic_centres.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False) 
    
    centre = relationship("DiagnosticCentre", back_populates="tests")
    bookings = relationship("Booking", back_populates="test")

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) 
    test_id = Column(Integer, ForeignKey("diagnostic_tests.id"), nullable=False) 
    centre_id = Column(Integer, ForeignKey("diagnostic_centres.id"), nullable=False) 
    appointment_date_time = Column(DateTime, nullable=False) 
    amount = Column(Float, nullable=False) 
    status = Column(SQLEnum(BookingStatus), default=BookingStatus.PENDING, nullable=False) 
    
    user = relationship("User", back_populates="bookings")
    test = relationship("DiagnosticTest", back_populates="bookings")
    centre = relationship("DiagnosticCentre", back_populates="bookings")
    payment_logs = relationship("PaymentLog", back_populates="booking")

class PaymentLog(Base):
    __tablename__ = "payment_logs"
    
    transaction_id = Column(String, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    status = Column(String, nullable=False)
    
    booking = relationship("Booking", back_populates="payment_logs")