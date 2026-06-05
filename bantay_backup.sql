CREATE DATABASE  IF NOT EXISTS `bantay` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `bantay`;
-- MySQL dump 10.13  Distrib 8.0.42, for Win64 (x86_64)
--
-- Host: localhost    Database: bantay
-- ------------------------------------------------------
-- Server version	8.0.41

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `active_patroller`
--

DROP TABLE IF EXISTS `active_patroller`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `active_patroller` (
  `active_patroller_id` int NOT NULL AUTO_INCREMENT,
  `officer_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_login` datetime DEFAULT NULL,
  PRIMARY KEY (`active_patroller_id`),
  UNIQUE KEY `active_patroller_officer_id_unique` (`officer_id`),
  CONSTRAINT `fk_active_patroller_officer` FOREIGN KEY (`officer_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `active_patroller`
--

LOCK TABLES `active_patroller` WRITE;
/*!40000 ALTER TABLE `active_patroller` DISABLE KEYS */;
/*!40000 ALTER TABLE `active_patroller` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `after_patrol_reports`
--

DROP TABLE IF EXISTS `after_patrol_reports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `after_patrol_reports` (
  `report_id` int NOT NULL AUTO_INCREMENT,
  `patrol_id` int NOT NULL,
  `submitted_by` int NOT NULL,
  `patrol_date` date NOT NULL,
  `shift` varchar(2) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time_from` time DEFAULT NULL,
  `time_to` time DEFAULT NULL,
  `pre_deployment` text COLLATE utf8mb4_unicode_ci,
  `action_pre_deployment` text COLLATE utf8mb4_unicode_ci,
  `incidents` text COLLATE utf8mb4_unicode_ci,
  `action_incidents` text COLLATE utf8mb4_unicode_ci,
  `safety_concerns` text COLLATE utf8mb4_unicode_ci,
  `action_safety` text COLLATE utf8mb4_unicode_ci,
  `other_services` text COLLATE utf8mb4_unicode_ci,
  `visited_areas` text COLLATE utf8mb4_unicode_ci,
  `persons_visited` text COLLATE utf8mb4_unicode_ci,
  `num_officials` int DEFAULT NULL,
  `num_govt_officials` int DEFAULT NULL,
  `sector_beat` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `must_dos` text COLLATE utf8mb4_unicode_ci,
  `credit_hours` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `remarks` text COLLATE utf8mb4_unicode_ci,
  `sig_officer_1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sig_officer_2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sig_supervisor` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `photo_urls` json DEFAULT NULL,
  `submitted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`report_id`),
  UNIQUE KEY `apr_unique_patroller_date` (`patrol_id`,`submitted_by`,`patrol_date`),
  UNIQUE KEY `apr_unique_patrol_date_shift` (`patrol_id`,`patrol_date`,`shift`),
  KEY `idx_apr_patrol_id` (`patrol_id`),
  KEY `idx_apr_submitted_by` (`submitted_by`),
  KEY `idx_apr_patrol_date` (`patrol_date`),
  CONSTRAINT `apr_patrol_fkey` FOREIGN KEY (`patrol_id`) REFERENCES `patrol_assignment` (`patrol_id`) ON DELETE CASCADE,
  CONSTRAINT `apr_submitted_by_fkey` FOREIGN KEY (`submitted_by`) REFERENCES `active_patroller` (`active_patroller_id`) ON DELETE RESTRICT,
  CONSTRAINT `apr_num_govt_check` CHECK ((`num_govt_officials` >= 0)),
  CONSTRAINT `apr_num_officials_check` CHECK ((`num_officials` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `after_patrol_reports`
--

LOCK TABLES `after_patrol_reports` WRITE;
/*!40000 ALTER TABLE `after_patrol_reports` DISABLE KEYS */;
/*!40000 ALTER TABLE `after_patrol_reports` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `log_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT (uuid()),
  `user_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'success',
  `source` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`),
  KEY `idx_audit_logs_action` (`action`),
  KEY `idx_audit_logs_created_at` (`created_at` DESC),
  KEY `idx_audit_logs_status` (`status`),
  KEY `idx_audit_logs_user_id` (`user_id`),
  CONSTRAINT `audit_logs_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
INSERT INTO `audit_logs` VALUES ('013478a8-5fd3-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Unlocked','Unlocked account for user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:28'),('07b9c563-5fd3-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Deactivated','Deactivated user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:39'),('0cf4d1a8-5f52-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-03 21:42:23'),('0f9c3bb4-5ec1-11f1-b8a0-005056c00001',NULL,'asdf','Login Failed','Account does not exist','LOGIN','failed','Web Portal','127.0.0.1','2026-06-03 04:24:30'),('0fd9bc39-5fd3-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Restored','Restored user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:53'),('1934e017-5f52-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 21:42:44'),('19fccaa0-5fd3-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID c42e226d-4ae7-4591-a88b-0e6ab5f3150c','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:06:10'),('1ab900c3-5fce-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Registered','Registered new police user \"pnpbetaadmin\" with role Administrator','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:30:24'),('1f8c92f3-5ec9-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-03 05:22:13'),('24ec1eac-5ec9-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 05:22:22'),('2b7dcf8c-5fd0-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Registered','Registered new barangay user \"brgyjuandelacruz\" with role Brgy. Captain','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:45:11'),('35732a6c-5f51-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-03 21:36:21'),('3a90e0ee-5f60-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Modus Created','Created modus \"Stabbing\" for MURDER','CREATE','success','Web Portal','127.0.0.1','2026-06-03 23:23:52'),('3affd455-5ec8-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 05:15:50'),('3c5e7b9a-5f51-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 21:36:33'),('40b4e4b9-5f60-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Modus Updated','Changes made with Modus ID 1: Stabbing (MURDER)','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 23:24:03'),('443f9718-5fce-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Verification Email Resent','Resent verification email to user \"pnpbetaadmin\" (ilaciojairusmiguel@gmail.com)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:31:33'),('45f7e6aa-5f60-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Modus Deactivated','Changes made with Modus ID 1: Stabbing (MURDER)','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 23:24:12'),('48618aff-5fc2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Mobile Unit Created','Created mobile unit \"Mobile Patrol 1\" (Car/Sedan · ABC 1234)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 11:05:46'),('4a9d2bdf-5f60-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Modus Restored','Changes made with Modus ID 1: Stabbing (MURDER)','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 23:24:19'),('4d5659d1-5fc2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Mobile Unit Updated','Updated mobile unit ID 1 — \"Mobile Patrol 1\" (Car/Sedan · ABC 123)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 11:05:55'),('5088c1ff-5fc2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Mobile Unit Deleted','Deleted mobile unit ID 1','DELETE','success','Web Portal','127.0.0.1','2026-06-04 11:06:00'),('546ef220-5fd3-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID c42e226d-4ae7-4591-a88b-0e6ab5f3150c','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:07:48'),('58c6d277-5fc2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Mobile Unit Created','Created mobile unit \"Mobile 1\" (Car/Sedan · ABC 1234)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 11:06:14'),('5a4bd4ea-5fd0-11f1-b3c8-005056c00001','c42e226d-4ae7-4591-a88b-0e6ab5f3150c','brgyjuandelacruz','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 12:46:29'),('72234e79-5fcf-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Verification Email Resent','Resent verification email to user \"pnpbetaadmin\" (ilaciojairusmiguel@gmail.com)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:40:00'),('7d9c9472-5fd0-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID c42e226d-4ae7-4591-a88b-0e6ab5f3150c','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 12:47:29'),('84a08205-5f54-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-03 22:00:03'),('8c1eed06-5f54-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 22:00:15'),('9234919a-5ec3-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 04:42:28'),('96e622f7-5f4f-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 21:24:46'),('98d545b6-5f5c-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Password Changed','Password changed via OTP verification','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 22:57:53'),('a886cf7c-5f5c-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 22:58:19'),('ae8ad540-5f58-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-03 22:29:51'),('afb5611b-5fcf-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Verification Email Resent','Resent verification email to user \"pnpbetaadmin\" (ilaciojairusmiguel@gmail.com)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:41:43'),('b275831e-5fbd-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 10:32:57'),('b5dfeab2-5f58-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-03 22:30:03'),('cc2f8162-5f58-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 22:30:41'),('d35d8022-5fce-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 12:35:33'),('e51698c2-5f5d-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Profile & Email Updated','Updated profile and changed email to jairus.oicali@gmail.com','UPDATE','success','Web Portal','127.0.0.1','2026-06-03 23:07:10'),('e8cd545d-5fce-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','Verification Email Resent','Resent verification email to user \"pnpbetaadmin\" (ilaciojairusmiguel@gmail.com)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 12:36:09'),('ed6aa841-5fcf-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','pnpbetaadmin','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 12:43:27'),('f4f15a60-5fd2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:08'),('fb0f6339-5fd2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Updated','Updated user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:18'),('feb61c65-5fd2-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','User Locked','Locked account for user ID bdf30fec-d503-4085-8b11-4b4e74498555','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 13:05:24');
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `barangay_details`
--

DROP TABLE IF EXISTS `barangay_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `barangay_details` (
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `barangay_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`user_id`),
  KEY `idx_barangay_details_barangay_code` (`barangay_code`),
  CONSTRAINT `barangay_details_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `barangay_details`
--

LOCK TABLES `barangay_details` WRITE;
/*!40000 ALTER TABLE `barangay_details` DISABLE KEYS */;
INSERT INTO `barangay_details` VALUES ('99f14253-5ebd-11f1-b8a0-005056c00001','042103046'),('c42e226d-4ae7-4591-a88b-0e6ab5f3150c','ANIBAN I');
/*!40000 ALTER TABLE `barangay_details` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crime_modus_reference`
--

DROP TABLE IF EXISTS `crime_modus_reference`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crime_modus_reference` (
  `id` int NOT NULL AUTO_INCREMENT,
  `crime_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `modus_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_crime_modus` (`crime_type`,`modus_name`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crime_modus_reference`
--

LOCK TABLES `crime_modus_reference` WRITE;
/*!40000 ALTER TABLE `crime_modus_reference` DISABLE KEYS */;
INSERT INTO `crime_modus_reference` VALUES (1,'MURDER','Stabbing','Stabs the victim with sharp object',1,'2026-06-03 15:23:52','2026-06-03 15:24:19');
/*!40000 ALTER TABLE `crime_modus_reference` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mobile_unit`
--

DROP TABLE IF EXISTS `mobile_unit`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mobile_unit` (
  `mobile_unit_id` int NOT NULL AUTO_INCREMENT,
  `mobile_unit_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `vehicle_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plate_number` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`mobile_unit_id`),
  UNIQUE KEY `mobile_unit_mobile_unit_name_key` (`mobile_unit_name`),
  UNIQUE KEY `mobile_unit_plate_number_key` (`plate_number`),
  KEY `mobile_unit_created_by_fkey` (`created_by`),
  CONSTRAINT `mobile_unit_created_by_fkey` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `mobile_unit_vehicle_type_check` CHECK ((`vehicle_type` in (_utf8mb4'Car/Sedan',_utf8mb4'SUV/Van')))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mobile_unit`
--

LOCK TABLES `mobile_unit` WRITE;
/*!40000 ALTER TABLE `mobile_unit` DISABLE KEYS */;
INSERT INTO `mobile_unit` VALUES (2,'Mobile 1','Car/Sedan','ABC 1234','99f14253-5ebd-11f1-b8a0-005056c00001','2026-06-04 03:06:14','2026-06-04 03:06:14');
/*!40000 ALTER TABLE `mobile_unit` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `officer_locations`
--

DROP TABLE IF EXISTS `officer_locations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `officer_locations` (
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `latitude` decimal(10,8) NOT NULL,
  `longitude` decimal(11,8) NOT NULL,
  `accuracy` double DEFAULT NULL,
  `heading` double DEFAULT NULL,
  `speed` double DEFAULT NULL,
  `is_on_duty` tinyint(1) NOT NULL DEFAULT '1',
  `location_name` text COLLATE utf8mb4_unicode_ci,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  KEY `idx_officer_locations_updated` (`updated_at` DESC),
  CONSTRAINT `officer_locations_user_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `officer_locations`
--

LOCK TABLES `officer_locations` WRITE;
/*!40000 ALTER TABLE `officer_locations` DISABLE KEYS */;
/*!40000 ALTER TABLE `officer_locations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `otp_requests`
--

DROP TABLE IF EXISTS `otp_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `otp_requests` (
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `otp_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `request_count` int NOT NULL DEFAULT '1',
  `last_request_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`email`),
  KEY `idx_otp_requests_email` (`email`),
  KEY `idx_otp_requests_expires_at` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `otp_requests`
--

LOCK TABLES `otp_requests` WRITE;
/*!40000 ALTER TABLE `otp_requests` DISABLE KEYS */;
INSERT INTO `otp_requests` VALUES ('invsysmarkitbot@gmail.com','233265','2026-06-03 04:42:11',3,'2026-06-03 04:40:11');
/*!40000 ALTER TABLE `otp_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `patrol_assignment`
--

DROP TABLE IF EXISTS `patrol_assignment`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patrol_assignment` (
  `patrol_id` int NOT NULL AUTO_INCREMENT,
  `patrol_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `mobile_unit_id` int NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `created_by` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`patrol_id`),
  KEY `patrol_assignment_mobile_unit_fkey` (`mobile_unit_id`),
  KEY `patrol_assignment_created_by_fkey` (`created_by`),
  CONSTRAINT `patrol_assignment_created_by_fkey` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `patrol_assignment_mobile_unit_fkey` FOREIGN KEY (`mobile_unit_id`) REFERENCES `mobile_unit` (`mobile_unit_id`) ON DELETE CASCADE,
  CONSTRAINT `valid_date_range` CHECK ((`end_date` >= `start_date`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment`
--

LOCK TABLES `patrol_assignment` WRITE;
/*!40000 ALTER TABLE `patrol_assignment` DISABLE KEYS */;
/*!40000 ALTER TABLE `patrol_assignment` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `patrol_assignment_patroller`
--

DROP TABLE IF EXISTS `patrol_assignment_patroller`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patrol_assignment_patroller` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patrol_id` int NOT NULL,
  `active_patroller_id` int NOT NULL,
  `shift` varchar(2) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'AM',
  `route_date` date DEFAULT NULL,
  `assigned_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `pap_patrol_fkey` (`patrol_id`),
  KEY `pap_patroller_fkey` (`active_patroller_id`),
  CONSTRAINT `pap_patrol_fkey` FOREIGN KEY (`patrol_id`) REFERENCES `patrol_assignment` (`patrol_id`) ON DELETE CASCADE,
  CONSTRAINT `pap_patroller_fkey` FOREIGN KEY (`active_patroller_id`) REFERENCES `active_patroller` (`active_patroller_id`) ON DELETE CASCADE,
  CONSTRAINT `patrol_assignment_patroller_shift_check` CHECK ((`shift` in (_utf8mb4'AM',_utf8mb4'PM')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment_patroller`
--

LOCK TABLES `patrol_assignment_patroller` WRITE;
/*!40000 ALTER TABLE `patrol_assignment_patroller` DISABLE KEYS */;
/*!40000 ALTER TABLE `patrol_assignment_patroller` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `patrol_assignment_route`
--

DROP TABLE IF EXISTS `patrol_assignment_route`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patrol_assignment_route` (
  `route_id` int NOT NULL AUTO_INCREMENT,
  `patrol_id` int NOT NULL,
  `route_date` date NOT NULL,
  `barangay` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `time_start` time DEFAULT NULL,
  `time_end` time DEFAULT NULL,
  `stop_order` int NOT NULL,
  `shift` varchar(2) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'AM',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`route_id`),
  KEY `par_patrol_fkey` (`patrol_id`),
  CONSTRAINT `par_patrol_fkey` FOREIGN KEY (`patrol_id`) REFERENCES `patrol_assignment` (`patrol_id`) ON DELETE CASCADE,
  CONSTRAINT `patrol_assignment_route_shift_check` CHECK ((`shift` in (_utf8mb4'AM',_utf8mb4'PM')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment_route`
--

LOCK TABLES `patrol_assignment_route` WRITE;
/*!40000 ALTER TABLE `patrol_assignment_route` DISABLE KEYS */;
/*!40000 ALTER TABLE `patrol_assignment_route` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pending_credentials`
--

DROP TABLE IF EXISTS `pending_credentials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pending_credentials` (
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `credentials` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  CONSTRAINT `pending_credentials_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pending_credentials`
--

LOCK TABLES `pending_credentials` WRITE;
/*!40000 ALTER TABLE `pending_credentials` DISABLE KEYS */;
/*!40000 ALTER TABLE `pending_credentials` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pnp_ranks`
--

DROP TABLE IF EXISTS `pnp_ranks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pnp_ranks` (
  `rank_id` int NOT NULL AUTO_INCREMENT,
  `rank_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `abbreviation` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `rank_order` int NOT NULL,
  PRIMARY KEY (`rank_id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pnp_ranks`
--

LOCK TABLES `pnp_ranks` WRITE;
/*!40000 ALTER TABLE `pnp_ranks` DISABLE KEYS */;
INSERT INTO `pnp_ranks` VALUES (1,'Patrolman / Patrolwoman','Pat',1),(2,'Police Corporal','PCpl',2),(3,'Police Staff Sergeant','PSSg',3);
/*!40000 ALTER TABLE `pnp_ranks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `role_id` int NOT NULL AUTO_INCREMENT,
  `role_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`role_id`),
  UNIQUE KEY `roles_role_name_key` (`role_name`),
  CONSTRAINT `roles_user_type_check` CHECK ((`user_type` in (_utf8mb4'police',_utf8mb4'barangay')))
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'Administrator','police'),(2,'Investigator','police'),(3,'Patrol','police'),(4,'Brgy. Captain','barangay'),(5,'Technical Administrator','police'),(6,'Brgy. Official','barangay');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tokens`
--

DROP TABLE IF EXISTS `tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tokens` (
  `token_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT (uuid()),
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `is_revoked` tinyint(1) NOT NULL DEFAULT '0',
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`token_id`),
  UNIQUE KEY `tokens_token_hash_key` (`token_hash`),
  KEY `idx_tokens_expires_at` (`expires_at`),
  KEY `idx_tokens_token_hash` (`token_hash`),
  KEY `idx_tokens_user_id` (`user_id`),
  CONSTRAINT `tokens_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tokens`
--

LOCK TABLES `tokens` WRITE;
/*!40000 ALTER TABLE `tokens` DISABLE KEYS */;
INSERT INTO `tokens` VALUES ('19347268-5f52-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','3620eaad4bd8cb7ca56e72dc8b2c07b267510894485631e5ebddae49305864ff','2026-06-04 13:42:44',1,'2026-06-03 22:00:03','2026-06-03 21:42:44'),('1ab82a2f-5fce-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','e4a96d5d3c65691f7d9728934887c725edcdb4439e104d328aa1044f7f03289b','2026-06-05 04:30:24',1,'2026-06-04 12:31:33','2026-06-04 12:30:24'),('24eba836-5ec9-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','285020f8ed8b38c505c88a2d7931e3c45f0c38d74432ed07612f1605aa544f4d','2026-06-03 21:22:23',1,'2026-06-03 22:57:53','2026-06-03 05:22:22'),('2b10b610-5fd0-11f1-b3c8-005056c00001','c42e226d-4ae7-4591-a88b-0e6ab5f3150c','2c9367ba02782066f4d0aede9f4f70dd0c295b2d7a17c83ebd34daa888ce2d93','2026-06-05 04:45:11',1,'2026-06-04 12:45:34','2026-06-04 12:45:10'),('3aff7329-5ec8-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','46b5de96ca853af51e8f891147c800776dd45fa704e80e045c554d206b0a682d','2026-06-03 21:15:50',1,'2026-06-03 05:22:13','2026-06-03 05:15:50'),('3c5e05d6-5f51-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','cc1092ddd03c178cc57e0df4829045497ad5f22a303368040c9f712bee5e2d3c','2026-06-04 13:36:33',1,'2026-06-03 21:42:23','2026-06-03 21:36:33'),('443ee3c1-5fce-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','22093b486fd27735b4f879d283aae5acff36ea3768f348ead2044fdb90a30713','2026-06-05 04:31:34',1,'2026-06-04 12:36:09','2026-06-04 12:31:33'),('5a4b8245-5fd0-11f1-b3c8-005056c00001','c42e226d-4ae7-4591-a88b-0e6ab5f3150c','f4f187f657dc5356b801ebe959f56aa3017959859137012bcd389fa2556bc7da','2026-06-05 04:46:30',0,NULL,'2026-06-04 12:46:29'),('6f731f26-5ebe-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','8c587ad7597170174dae10758634c388dda3cb39e9ea58b7cb777d517ece9909','2026-06-03 20:05:43',1,'2026-06-03 04:06:10','2026-06-03 04:05:43'),('71abf0b2-5fcf-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','b535cb2194e3a07323a16ddbd7bb31b9c1a6e0841ce2c97ce9ec9643174326d3','2026-06-05 04:40:00',1,'2026-06-04 12:41:42','2026-06-04 12:39:59'),('8c1e5b46-5f54-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','e882f2ec457a1cca48415c809cc56bfb8ec22bd05166f01c235781b4243ab2b6','2026-06-04 14:00:16',1,'2026-06-03 22:29:51','2026-06-03 22:00:15'),('92342813-5ec3-11f1-b8a0-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','2ce8f2c8afa22acba626897f70385d4e148df6c5983a83c14ed173ce93fa81a3','2026-06-03 20:42:29',1,'2026-06-03 22:57:53','2026-06-03 04:42:28'),('96e429c2-5f4f-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','7be848851475df41dbbba645bb0e2913064bffd547fe732c94dd901f03a0d13e','2026-06-04 13:24:46',1,'2026-06-03 21:36:21','2026-06-03 21:24:46'),('a8867146-5f5c-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','621439aa1651e2c45dccce025ae05707b37af22ce02e1f5621b64eba27614b78','2026-06-04 14:58:19',0,NULL,'2026-06-03 22:58:19'),('af524a0e-5fcf-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','7923114a1a8e1389d610d6b4364bb0226641dca1e4e506f2b3ce221674136911','2026-06-05 04:41:43',1,'2026-06-04 12:41:51','2026-06-04 12:41:42'),('b274ec86-5fbd-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','e688b5c8597c6062403bcf27788350dc78f5ab890495d38beddcbf7e77e73e3f','2026-06-05 02:32:57',0,NULL,'2026-06-04 10:32:57'),('b5df83af-5f58-11f1-b3c8-005056c00001','99f14253-5ebd-11f1-b8a0-005056c00001','16df0714e70b659895f0f299f563d074d28b09ada1ca9940213f2d55e7af1c03','2026-06-04 14:30:04',1,'2026-06-03 22:57:53','2026-06-03 22:30:03'),('e8ccaee2-5fce-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','5d89f7081013531524b76617109715b13fdfc315a95d2d197191e909f5859a8d','2026-06-05 04:36:10',1,'2026-06-04 12:39:59','2026-06-04 12:36:09'),('ed6a48b4-5fcf-11f1-b3c8-005056c00001','bdf30fec-d503-4085-8b11-4b4e74498555','15eaf7e19fc94cfa4d3bef7dc00075b62707765a48b08b5ed38244d87fe58597','2026-06-05 04:43:27',0,NULL,'2026-06-04 12:43:27');
/*!40000 ALTER TABLE `tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_addresses`
--

DROP TABLE IF EXISTS `user_addresses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_addresses` (
  `address_id` int NOT NULL AUTO_INCREMENT,
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `region_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `province_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `municipality_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `barangay_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `address_line` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`address_id`),
  UNIQUE KEY `user_addresses_user_id_key` (`user_id`),
  KEY `idx_user_addresses_user_id` (`user_id`),
  KEY `idx_user_addresses_barangay_code` (`barangay_code`),
  KEY `idx_user_addresses_municipality_code` (`municipality_code`),
  CONSTRAINT `user_addresses_user_id_fkey` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=217 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_addresses`
--

LOCK TABLES `user_addresses` WRITE;
/*!40000 ALTER TABLE `user_addresses` DISABLE KEYS */;
INSERT INTO `user_addresses` VALUES (210,'99f14253-5ebd-11f1-b8a0-005056c00001','040000000','042100000','042103000','042103046','BLk 2 Lot 17 Medina Street Phase 2A'),(215,'bdf30fec-d503-4085-8b11-4b4e74498555','040000000','042100000','042103000','042103004',NULL),(216,'c42e226d-4ae7-4591-a88b-0e6ab5f3150c','040000000','042100000','042103000','ANIBAN I',NULL);
/*!40000 ALTER TABLE `user_addresses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT (uuid()),
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `first_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `middle_name` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `suffix` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(15) COLLATE utf8mb4_unicode_ci NOT NULL,
  `alternate_phone` varchar(15) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `gender` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `date_of_birth` date NOT NULL,
  `role_id` int NOT NULL,
  `user_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `profile_picture` text COLLATE utf8mb4_unicode_ci,
  `status` varchar(15) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unverified',
  `lockout_until` datetime DEFAULT NULL,
  `failed_login_attempts` int NOT NULL DEFAULT '0',
  `last_login` datetime DEFAULT NULL,
  `created_by` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `email_changed_at` datetime DEFAULT NULL,
  `password_changed_at` datetime DEFAULT NULL,
  `pw_change_count` int NOT NULL DEFAULT '0',
  `pw_window_start` bigint DEFAULT NULL,
  `rank_id` int DEFAULT NULL,
  `push_token` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `users_email_key` (`email`),
  UNIQUE KEY `users_phone_key` (`phone`),
  UNIQUE KEY `users_username_key` (`username`),
  KEY `users_created_by_fkey` (`created_by`),
  KEY `idx_users_email` (`email`),
  KEY `idx_users_rank_id` (`rank_id`),
  KEY `idx_users_role_id` (`role_id`),
  KEY `idx_users_status` (`status`),
  KEY `idx_users_user_type` (`user_type`),
  KEY `idx_users_username` (`username`),
  CONSTRAINT `users_created_by_fkey` FOREIGN KEY (`created_by`) REFERENCES `users` (`user_id`) ON DELETE SET NULL,
  CONSTRAINT `users_rank_id_fkey` FOREIGN KEY (`rank_id`) REFERENCES `pnp_ranks` (`rank_id`) ON DELETE RESTRICT,
  CONSTRAINT `users_role_id_fkey` FOREIGN KEY (`role_id`) REFERENCES `roles` (`role_id`) ON DELETE RESTRICT,
  CONSTRAINT `users_status_check` CHECK ((`status` in (_utf8mb4'verified',_utf8mb4'unverified',_utf8mb4'locked',_utf8mb4'deactivated'))),
  CONSTRAINT `users_user_type_check` CHECK ((`user_type` in (_utf8mb4'police',_utf8mb4'barangay')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES ('99f14253-5ebd-11f1-b8a0-005056c00001','II26010_pnp','SecurePass123!','jairus.oicali@gmail.com','Juan','Dela Cruz','Santos',NULL,'+639171234567',NULL,'Male','1990-06-15',5,'police','/uploads/profiles/99f14253-5ebd-11f1-b8a0-005056c00001_94050f4fea1a41e7b0e44013270a0ae5.png','verified',NULL,0,'2026-06-04 10:32:57',NULL,'2026-06-03 03:59:44','2026-06-04 13:07:19','2026-06-03 23:07:10','2026-06-03 22:57:53',1,1780498673068,NULL,NULL),('bdf30fec-d503-4085-8b11-4b4e74498555','pnpbetaadmin','SecurePass123!','ilaciojairusmiguel@gmail.com','Beta','Admin',NULL,NULL,'+639102349802',NULL,'Male','2008-06-03',1,'police',NULL,'verified',NULL,0,'2026-06-04 12:43:27',NULL,'2026-06-04 12:30:24','2026-06-04 13:07:19',NULL,NULL,0,NULL,2,NULL),('c42e226d-4ae7-4591-a88b-0e6ab5f3150c','brgyjuandelacruz','SecurePass123!','jairusmiguelilacio05@gmail.com','Juan','Dela cruz',NULL,NULL,'+639123941092',NULL,'Male','2008-06-03',4,'barangay',NULL,'verified',NULL,0,'2026-06-04 12:46:29',NULL,'2026-06-04 12:45:10','2026-06-04 13:07:48',NULL,NULL,0,NULL,NULL,NULL);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-04 13:27:47
