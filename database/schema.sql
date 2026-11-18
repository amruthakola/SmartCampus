CREATE DATABASE IF NOT EXISTS smart_campus;
USE smart_campus;
CREATE TABLE IF NOT EXISTS users (
 id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(150) UNIQUE NOT NULL,
 role ENUM('ADMIN','MANAGER','TECHNICIAN','APPROVER','FACULTY','STUDENT') NOT NULL
);
CREATE TABLE IF NOT EXISTS facilities (
 id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL, location VARCHAR(150),
 capacity INT NOT NULL DEFAULT 1, facility_type VARCHAR(60) NOT NULL, restricted BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS bookings (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, facility_id INT NOT NULL, user_name VARCHAR(100) NOT NULL,
 start_time DATETIME NOT NULL, end_time DATETIME NOT NULL, purpose VARCHAR(255) NOT NULL,
 status ENUM('REQUESTED','APPROVED','CONFIRMED','IN_USE','COMPLETED','CANCELLED') NOT NULL,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_booking_facility FOREIGN KEY(facility_id) REFERENCES facilities(id),
 INDEX idx_booking_overlap(facility_id,start_time,end_time,status)
);
CREATE TABLE IF NOT EXISTS tickets (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(180) NOT NULL, description TEXT NOT NULL,
 category VARCHAR(40) NOT NULL, priority VARCHAR(20) NOT NULL,
 status ENUM('OPEN','ASSIGNED','INSPECTION','PENDING_WORK','RESOLVED','CLOSED') NOT NULL,
 reported_by VARCHAR(100) NOT NULL, assigned_to VARCHAR(100), inspection_notes TEXT, resolution TEXT,
 source_event_id VARCHAR(120) UNIQUE NULL, version INT NOT NULL DEFAULT 1,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS approvals (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, request_type VARCHAR(40) NOT NULL, request_id BIGINT NOT NULL,
 requested_by VARCHAR(100) NOT NULL, status ENUM('PENDING','APPROVED','REJECTED') NOT NULL,
 decided_by VARCHAR(100), comments TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_logs (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, actor VARCHAR(100) NOT NULL, action VARCHAR(80) NOT NULL,
 entity_type VARCHAR(50) NOT NULL, entity_id BIGINT NOT NULL, details TEXT,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT IGNORE INTO facilities(id,name,location,capacity,facility_type,restricted) VALUES
(1,'Central Seminar Hall','Main Block - Ground Floor',120,'HALL',FALSE),
(2,'Computer Laboratory 1','Technology Block - First Floor',40,'LAB',TRUE),
(3,'Project Discussion Room','Library Block - Second Floor',12,'MEETING ROOM',FALSE),
(4,'Physics Laboratory','Science Block - Ground Floor',30,'LAB',TRUE);
