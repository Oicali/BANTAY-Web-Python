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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `active_patroller`
--

LOCK TABLES `active_patroller` WRITE;
/*!40000 ALTER TABLE `active_patroller` DISABLE KEYS */;
INSERT INTO `active_patroller` VALUES (1,'4620ed6a-6afb-41d7-83a5-caeab4931daf',NULL),(3,'18ce28cf-5255-4d61-96cc-f9fbf559d68a',NULL);
/*!40000 ALTER TABLE `active_patroller` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trigger_check_patroller_role` BEFORE INSERT ON `active_patroller` FOR EACH ROW BEGIN
    DECLARE v_role_id INT;

    SELECT role_id INTO v_role_id
    FROM users
    WHERE user_id = NEW.officer_id
    LIMIT 1;

    IF v_role_id != 3 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'User is not a patroller. Only users with role_id = 3 can be added as active patrollers.';
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

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
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `after_patrol_reports`
--

LOCK TABLES `after_patrol_reports` WRITE;
/*!40000 ALTER TABLE `after_patrol_reports` DISABLE KEYS */;
INSERT INTO `after_patrol_reports` VALUES (7,1,3,'2026-06-04','AM','08:00:00','20:00:00','','','','','','','','','',NULL,NULL,'Mobile Patrol 1','','12 hrs','asdfasdf','','','','[\"/uploads/patrol_reports/report_7_53bf88dae699445b831922b25a941049.jpeg\"]','2026-06-04 14:51:39','2026-06-04 14:51:39');
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
INSERT INTO `audit_logs` VALUES ('07dead21-6006-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:10:44'),('0d21818f-6024-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Created','Created patrol \"Sector 2 Beat 1\" (2026-06-10 – 2026-06-17)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 22:45:38'),('1bf6b897-6021-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Password Reset','Password reset via OTP for jairus.oicali@gmail.com','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 22:24:34'),('228fb862-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Modus Created','Created modus \"Akyat Bahay\" for THEFT','CREATE','success','Web Portal','127.0.0.1','2026-06-04 22:39:04'),('277e8b7a-6009-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:33:05'),('28d853b1-6021-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 22:24:56'),('296a7d21-5ffb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Deleted','Deleted patrol ID 3','DELETE','success','Web Portal','127.0.0.1','2026-06-04 17:52:56'),('2e74d132-5ff8-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Updated','Updated patrol ID 1 — \"Sector 1 Beat 1\" (2026-06-04 – 2026-06-07)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 17:31:36'),('36349dc6-5fff-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:21:55'),('38831cee-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Modus Deactivated','Changes made with Modus ID 1: Akyat Bahay (THEFT)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 22:39:41'),('3b37a333-5ffb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Created','Created patrol \"Sector 1 Beat 3\" (2026-06-14 – 2026-06-17)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 17:53:26'),('41a61d99-5ffb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Detail Export Failed','Invalid format string','EXPORT','failed','Web Portal','127.0.0.1','2026-06-04 17:53:36'),('41fa16a8-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Modus Restored','Changes made with Modus ID 1: Akyat Bahay (THEFT)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 22:39:57'),('42c9f9af-5ff8-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Created','Created patrol \"Sector 1 Beat 2\" (2026-06-10 – 2026-06-17)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 17:32:10'),('474ef887-6029-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-04 23:23:03'),('4dab1855-6000-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Detail Exported','Exported patrol detail — \"Sector 1 Beat 1\"','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:29:44'),('4f478005-6029-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 23:23:16'),('4f66a67e-5ffe-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 18:15:28'),('4fce8aa2-5fec-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Registered','Registered new police user \"pnpbetapatrol\" with role Patrol','CREATE','success','Web Portal','127.0.0.1','2026-06-04 16:06:38'),('5242c3ce-6006-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 19:12:49'),('53e02659-5ffe-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:15:35'),('5cfa2ac3-5fef-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Registered','Registered new police user \"pnpcharliepatrol\" with role Patrol','CREATE','success','Web Portal','127.0.0.1','2026-06-04 16:28:28'),('65b21679-6024-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 22:48:06'),('6882db1a-5fef-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Updated','Updated user ID 18ce28cf-5255-4d61-96cc-f9fbf559d68a','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 16:28:48'),('6e12ea77-6022-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Registered','Registered new police user \"pnpbetainvestigator\" with role Investigator','CREATE','success','Web Portal','127.0.0.1','2026-06-04 22:34:01'),('7b3bedd5-5fee-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Verification Email Resent','Resent verification email to user \"pnpbetapatrol\" (ilaciojairus@gmail.com)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 16:22:09'),('8980b3ae-6007-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:21:31'),('90682277-6000-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:31:36'),('9252ac51-6021-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 22:27:53'),('95b0455e-6005-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-04 19:07:32'),('9694dbbe-6022-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Deactivated','Deactivated user ID 094fbd21-0396-4b12-a0d9-23c9ddc5ed12','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 22:35:09'),('9abee0ff-5fff-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:24:44'),('9b44850b-5feb-11f1-b3c8-005056c00001',NULL,'II26010_pnp','Login Failed','Account does not exist','LOGIN','failed','Web Portal','127.0.0.1','2026-06-04 16:01:35'),('9e1107e4-6005-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 19:07:46'),('a3851c63-6003-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Updated','Updated patrol ID 1 — \"Sector 1 Beat 1\" (2026-06-04 – 2026-06-07)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 18:53:36'),('a63b2e6b-5ff9-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 17:42:06'),('a653c5d9-6009-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:36:38'),('aa08bb59-5ff9-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 17:42:12'),('adc9fa6d-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Mobile Unit Created','Created mobile unit \"Mobile Unit 2\" (SUV/Van · DEF 5678)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 22:42:58'),('b97e8ad6-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Mobile Unit Deleted','Deleted mobile unit ID 2','DELETE','success','Web Portal','127.0.0.1','2026-06-04 22:43:17'),('bd8966a8-6005-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:08:39'),('bfbd2391-5ffd-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 2 patrol(s) (1 active, 1 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:11:27'),('c0d1485d-5ff7-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Created','Created patrol \"Sector 1 Beat 1\" (2026-06-04 – 2026-06-11)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 17:28:32'),('c150d2c8-6003-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Updated','Updated user ID 18ce28cf-5255-4d61-96cc-f9fbf559d68a','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 18:54:26'),('c227e5ae-6023-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Mobile Unit Created','Created mobile unit \"Mobile Patrol 2\" (SUV/Van · DEF 5678)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 22:43:32'),('c26c75bb-5feb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 16:02:40'),('c615dedb-608a-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-05 11:00:57'),('c9070c2c-6007-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 19:23:17'),('c98526eb-5fff-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:26:02'),('ce2776c0-5ffa-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Updated','Updated patrol ID 2 — \"Sector 1 Beat 2\" (2026-06-10 – 2026-06-13)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 17:50:23'),('d096db25-5fee-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Updated','Updated user ID 4620ed6a-6afb-41d7-83a5-caeab4931daf','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 16:24:33'),('d140cc5b-6020-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-04 22:22:29'),('d658ba5e-5fee-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Updated','Updated user ID 4620ed6a-6afb-41d7-83a5-caeab4931daf','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 16:24:42'),('dafed5f2-6024-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Deleted','Deleted after patrol report ID 6','DELETE','success','Web Portal','127.0.0.1','2026-06-04 22:51:23'),('ddb5246b-6004-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Updated','Updated patrol ID 1 — \"Sector 1 Beat 1\" (2026-06-04 – 2026-06-07)','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 19:02:24'),('e00c4075-5fff-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:26:40'),('e06f5b13-5ffd-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Detail Exported','Exported patrol detail — \"Sector 1 Beat 1\"','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:12:22'),('e2fc77fa-5fff-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:26:45'),('e32f0627-5feb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Profile Updated','Updated profile','UPDATE','success','Web Portal','127.0.0.1','2026-06-04 16:03:35'),('e49e3e99-6024-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','After Patrol Report Submitted','Submitted after patrol report for patrol ID 1 — 2026-06-04 AM','CREATE','success','Mobile App','127.0.0.1','2026-06-04 22:51:39'),('e4c66032-5fef-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Mobile Unit Created','Created mobile unit \"Mobile Patrol 1\" (Car/Sedan · ABC 1234)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 16:32:16'),('e556d812-5ffa-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol Created','Created patrol \"Sector 1 Beat 3\" (2026-06-14 – 2026-06-17)','CREATE','success','Web Portal','127.0.0.1','2026-06-04 17:51:01'),('e7ca0efc-6004-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Logout','User logged out','LOGOUT','success','Web Portal','127.0.0.1','2026-06-04 19:02:41'),('e92e8c4c-5ffe-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','Patrol List Exported','Exported patrol list — 3 patrol(s) (1 active, 2 upcoming, 0 completed)','EXPORT','success','Web Portal','127.0.0.1','2026-06-04 18:19:46'),('f98ade97-6005-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','User Login','Logged in via web portal','LOGIN','success','Web Portal','127.0.0.1','2026-06-04 19:10:20');
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
INSERT INTO `barangay_details` VALUES ('6cbc1427-5feb-11f1-b3c8-005056c00001','042103046');
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
INSERT INTO `crime_modus_reference` VALUES (1,'THEFT','Akyat Bahay','Suspect targets a house',1,'2026-06-04 14:39:04','2026-06-04 14:39:57');
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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mobile_unit`
--

LOCK TABLES `mobile_unit` WRITE;
/*!40000 ALTER TABLE `mobile_unit` DISABLE KEYS */;
INSERT INTO `mobile_unit` VALUES (1,'Mobile Patrol 1','Car/Sedan','ABC 1234','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 08:32:16','2026-06-04 08:32:16'),(3,'Mobile Patrol 2','SUV/Van','DEF 5678','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 14:43:32','2026-06-04 14:43:32');
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
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment`
--

LOCK TABLES `patrol_assignment` WRITE;
/*!40000 ALTER TABLE `patrol_assignment` DISABLE KEYS */;
INSERT INTO `patrol_assignment` VALUES (1,'Sector 1 Beat 1',1,'2026-06-04','2026-06-07','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 09:28:32','2026-06-04 11:02:24'),(2,'Sector 1 Beat 2',1,'2026-06-10','2026-06-13','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 09:32:10','2026-06-04 09:50:23'),(4,'Sector 1 Beat 3',1,'2026-06-14','2026-06-17','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 09:53:25','2026-06-04 09:53:25'),(5,'Sector 2 Beat 1',3,'2026-06-10','2026-06-17','6cbc1427-5feb-11f1-b3c8-005056c00001','2026-06-04 14:45:37','2026-06-04 14:45:37');
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
) ENGINE=InnoDB AUTO_INCREMENT=41 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment_patroller`
--

LOCK TABLES `patrol_assignment_patroller` WRITE;
/*!40000 ALTER TABLE `patrol_assignment_patroller` DISABLE KEYS */;
INSERT INTO `patrol_assignment_patroller` VALUES (5,1,1,'AM','2026-06-08','2026-06-04 09:28:32'),(6,1,1,'AM','2026-06-09','2026-06-04 09:28:32'),(7,1,1,'AM','2026-06-10','2026-06-04 09:28:32'),(8,1,1,'AM','2026-06-11','2026-06-04 09:28:32'),(9,2,1,'AM','2026-06-10','2026-06-04 09:32:10'),(10,2,1,'AM','2026-06-11','2026-06-04 09:32:10'),(11,2,1,'AM','2026-06-12','2026-06-04 09:32:10'),(12,2,1,'AM','2026-06-13','2026-06-04 09:32:10'),(13,2,1,'AM','2026-06-14','2026-06-04 09:32:10'),(14,2,1,'AM','2026-06-15','2026-06-04 09:32:10'),(15,2,1,'AM','2026-06-16','2026-06-04 09:32:10'),(16,2,1,'AM','2026-06-17','2026-06-04 09:32:10'),(21,4,1,'AM','2026-06-14','2026-06-04 09:53:26'),(22,4,1,'AM','2026-06-15','2026-06-04 09:53:26'),(23,4,1,'AM','2026-06-16','2026-06-04 09:53:26'),(24,4,1,'AM','2026-06-17','2026-06-04 09:53:26'),(25,1,1,'AM','2026-06-04','2026-06-04 11:02:23'),(26,1,3,'AM','2026-06-04','2026-06-04 11:02:23'),(27,1,1,'AM','2026-06-05','2026-06-04 11:02:23'),(28,1,3,'AM','2026-06-05','2026-06-04 11:02:23'),(29,1,1,'AM','2026-06-06','2026-06-04 11:02:23'),(30,1,3,'AM','2026-06-06','2026-06-04 11:02:23'),(31,1,1,'AM','2026-06-07','2026-06-04 11:02:23'),(32,1,3,'AM','2026-06-07','2026-06-04 11:02:23'),(33,5,3,'AM','2026-06-10','2026-06-04 14:45:38'),(34,5,3,'AM','2026-06-11','2026-06-04 14:45:38'),(35,5,3,'AM','2026-06-12','2026-06-04 14:45:38'),(36,5,3,'AM','2026-06-13','2026-06-04 14:45:38'),(37,5,3,'AM','2026-06-14','2026-06-04 14:45:38'),(38,5,3,'AM','2026-06-15','2026-06-04 14:45:38'),(39,5,3,'AM','2026-06-16','2026-06-04 14:45:38'),(40,5,3,'AM','2026-06-17','2026-06-04 14:45:38');
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
) ENGINE=InnoDB AUTO_INCREMENT=96 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `patrol_assignment_route`
--

LOCK TABLES `patrol_assignment_route` WRITE;
/*!40000 ALTER TABLE `patrol_assignment_route` DISABLE KEYS */;
INSERT INTO `patrol_assignment_route` VALUES (4,1,'2026-06-04',NULL,'Tasksssss 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(5,1,'2026-06-04',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(6,1,'2026-06-04',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(7,1,'2026-06-05',NULL,'Tasksssss 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(8,1,'2026-06-05',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(9,1,'2026-06-05',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(10,1,'2026-06-06',NULL,'Tasksssss 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(11,1,'2026-06-06',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(12,1,'2026-06-06',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(13,1,'2026-06-07',NULL,'Tasksssss 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(14,1,'2026-06-07',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(15,1,'2026-06-07',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(16,1,'2026-06-08',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(17,1,'2026-06-08',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(18,1,'2026-06-08',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(19,1,'2026-06-09',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(20,1,'2026-06-09',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(21,1,'2026-06-09',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(22,1,'2026-06-10',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(23,1,'2026-06-10',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(24,1,'2026-06-10',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(25,1,'2026-06-11',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:28:32'),(26,1,'2026-06-11',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:28:32'),(27,1,'2026-06-11',NULL,'Task 3','10:01:00','11:00:00',3,'AM','2026-06-04 09:28:32'),(28,1,'2026-06-04',NULL,'Task 4','11:01:00','12:00:00',4,'AM','2026-06-04 09:31:15'),(29,1,'2026-06-05',NULL,'Task 4','11:01:00','12:00:00',4,'AM','2026-06-04 09:31:34'),(30,1,'2026-06-06',NULL,'Task 4','11:01:00','12:00:00',4,'AM','2026-06-04 09:31:35'),(31,1,'2026-06-07',NULL,'Task 4','11:01:00','12:00:00',4,'AM','2026-06-04 09:31:35'),(38,2,'2026-06-10',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(39,2,'2026-06-10',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(40,2,'2026-06-11',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(41,2,'2026-06-11',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(42,2,'2026-06-12',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(43,2,'2026-06-12',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(44,2,'2026-06-13',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(45,2,'2026-06-13',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(46,2,'2026-06-14',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(47,2,'2026-06-14',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(48,2,'2026-06-15',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(49,2,'2026-06-15',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(50,2,'2026-06-16',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(51,2,'2026-06-16',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(52,2,'2026-06-17',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:32:10'),(53,2,'2026-06-17',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 09:32:10'),(54,2,'2026-06-10','HABAY I',NULL,NULL,NULL,-1,'AM','2026-06-04 09:50:23'),(55,2,'2026-06-10','MABOLO',NULL,NULL,NULL,-2,'AM','2026-06-04 09:50:23'),(56,2,'2026-06-10','SINEGUELASAN',NULL,NULL,NULL,-3,'AM','2026-06-04 09:50:23'),(64,4,'2026-06-14','MAMBOG I',NULL,NULL,NULL,-1,'AM','2026-06-04 09:53:26'),(65,4,'2026-06-14','MAMBOG II',NULL,NULL,NULL,-2,'AM','2026-06-04 09:53:26'),(66,4,'2026-06-14','MAMBOG III',NULL,NULL,NULL,-3,'AM','2026-06-04 09:53:26'),(67,4,'2026-06-14',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:53:26'),(68,4,'2026-06-15',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:53:26'),(69,4,'2026-06-16',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:53:26'),(70,4,'2026-06-17',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 09:53:26'),(74,1,'2026-06-04','MAMBOG III',NULL,NULL,NULL,-1,'AM','2026-06-04 11:02:24'),(75,1,'2026-06-04','MAMBOG II',NULL,NULL,NULL,-2,'AM','2026-06-04 11:02:24'),(76,1,'2026-06-04','MAMBOG I',NULL,NULL,NULL,-3,'AM','2026-06-04 11:02:24'),(77,5,'2026-06-10','MOLINO VII',NULL,NULL,NULL,-1,'AM','2026-06-04 14:45:38'),(78,5,'2026-06-10','MOLINO III',NULL,NULL,NULL,-2,'AM','2026-06-04 14:45:38'),(79,5,'2026-06-10','MOLINO IV',NULL,NULL,NULL,-3,'AM','2026-06-04 14:45:38'),(80,5,'2026-06-10',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(81,5,'2026-06-10',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(82,5,'2026-06-11',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(83,5,'2026-06-11',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(84,5,'2026-06-12',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(85,5,'2026-06-12',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(86,5,'2026-06-13',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(87,5,'2026-06-13',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(88,5,'2026-06-14',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(89,5,'2026-06-14',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(90,5,'2026-06-15',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(91,5,'2026-06-15',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(92,5,'2026-06-16',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(93,5,'2026-06-16',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38'),(94,5,'2026-06-17',NULL,'Task 1','08:00:00','09:00:00',1,'AM','2026-06-04 14:45:38'),(95,5,'2026-06-17',NULL,'Task 2','09:01:00','10:00:00',2,'AM','2026-06-04 14:45:38');
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
INSERT INTO `pending_credentials` VALUES ('094fbd21-0396-4b12-a0d9-23c9ddc5ed12','{\"username\": \"pnpbetainvestigator\", \"password\": \"LT4ozx$Y@GYU\", \"userType\": \"police\", \"role\": \"Investigator\"}','2026-06-05 14:34:01','2026-06-04 22:34:00'),('18ce28cf-5255-4d61-96cc-f9fbf559d68a','{\"username\": \"pnpcharliepatrol\", \"password\": \"LNRv9QSgHKW5\", \"userType\": \"police\", \"role\": \"Patrol\"}','2026-06-05 08:28:28','2026-06-04 16:28:27'),('4620ed6a-6afb-41d7-83a5-caeab4931daf','{\"username\": \"pnpbetapatrol\", \"password\": \"XCZp9k$3Q?Hb\", \"userType\": \"police\", \"role\": \"Patrol\"}','2026-06-05 08:22:09','2026-06-04 16:06:37');
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
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pnp_ranks`
--

LOCK TABLES `pnp_ranks` WRITE;
/*!40000 ALTER TABLE `pnp_ranks` DISABLE KEYS */;
INSERT INTO `pnp_ranks` VALUES (1,'Patrolman / Patrolwoman','Pat',1),(2,'Police Corporal','PCpl',2),(3,'Police Staff Sergeant','PSSg',3),(4,'Police Master Sergeant','PMSg',4),(5,'Police Senior Master Sergeant','PSMSg',5),(6,'Police Chief Master Sergeant','PCMSg',6),(7,'Police Executive Master Sergeant','PEMSg',7),(8,'Police Lieutenant Junior Grade','PLTJG',8),(9,'Police Lieutenant','PLT',9),(10,'Police Captain','PCPT',10),(11,'Police Major','PMAJ',11),(12,'Police Lieutenant Colonel','PLTCOL',12),(13,'Police Colonel','PCOL',13),(14,'Police Brigadier General','PBGEN',14),(15,'Police Major General','PMGEN',15),(16,'Police Lieutenant General','PLTGEN',16),(17,'Police General','PGEN',17);
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
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'Technical Administrator','police'),(2,'Administrator','police'),(3,'Patrol','police'),(4,'Investigator','police'),(5,'Brgy. Captain','barangay'),(6,'Brgy. Official','barangay');
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
INSERT INTO `tokens` VALUES ('28d7f1ab-6021-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','c69399d5b9b83543e479bf6977682f9dbcca92279768a9a78e2804856a0f8d39','2026-06-05 14:24:56',0,NULL,'2026-06-04 22:24:56'),('4f4682c8-6029-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','8f510efd598798662f888852d067fb4fb81934eebfbc67186deecadf497d4fc9','2026-06-05 15:23:17',0,NULL,'2026-06-04 23:23:16'),('4f58b455-5fec-11f1-b3c8-005056c00001','4620ed6a-6afb-41d7-83a5-caeab4931daf','d18bcc289c38261c668993c8fac3bb653f2542fecb37066a288b796f5dcb37b6','2026-06-05 08:06:37',1,'2026-06-04 16:22:09','2026-06-04 16:06:37'),('4f6649f7-5ffe-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','35c8b6842c558f9d89e503fa71e960e6138567853a8c59e000d6f8a4c7292fd6','2026-06-05 10:15:28',1,'2026-06-04 19:02:41','2026-06-04 18:15:28'),('5c8d529b-5fef-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','e4ee1a8f1b7b747b0a73619eead131174288a0c547b3efc53bc1a900e0b282a6','2026-06-05 08:28:28',0,NULL,'2026-06-04 16:28:27'),('65b1bcba-6024-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','d9c44bcde02b8b18a473a82bf3743f5731d7d396620eee5ee63cf182d37b1170','2026-06-05 14:48:07',1,'2026-06-04 23:23:03','2026-06-04 22:48:06'),('6d97fcb4-6022-11f1-b3c8-005056c00001','094fbd21-0396-4b12-a0d9-23c9ddc5ed12','9a2d241f283c5ee46d38003614f24dad1d4424c4b4687844379750c4fe7588cb','2026-06-05 14:34:01',0,NULL,'2026-06-04 22:34:00'),('7ac62a87-5fee-11f1-b3c8-005056c00001','4620ed6a-6afb-41d7-83a5-caeab4931daf','fd872a080994147740f2e9019d27516b11f855f8104fd2c7b795eebce9e0f1a4','2026-06-05 08:22:09',0,NULL,'2026-06-04 16:22:09'),('9e1077e1-6005-11f1-b3c8-005056c00001','18ce28cf-5255-4d61-96cc-f9fbf559d68a','b605c6914a736d9955a2dd269ae975a1590ad71865ebb1dd08c1ad99b47322f8','2026-06-05 11:07:47',0,NULL,'2026-06-04 19:07:46'),('c26bec18-5feb-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','265a652790b6c62bde90ea83b759cf8e59404f76a9bf315c46696ac95102f980','2026-06-05 08:02:41',1,'2026-06-04 19:07:32','2026-06-04 16:02:40'),('c6157129-608a-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','de736acfbd05c89920d6f8b6ae9138eacaa587b8af77a4fcdb7e2ea1ab1c1da1','2026-06-06 03:00:57',0,NULL,'2026-06-05 11:00:57'),('f98a79dd-6005-11f1-b3c8-005056c00001','6cbc1427-5feb-11f1-b3c8-005056c00001','c33e03164793c0aae8ca0b0118b38278004ebe7a83f5a1210d4f4ebe79a1c6c4','2026-06-05 11:10:20',1,'2026-06-04 22:22:29','2026-06-04 19:10:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_addresses`
--

LOCK TABLES `user_addresses` WRITE;
/*!40000 ALTER TABLE `user_addresses` DISABLE KEYS */;
INSERT INTO `user_addresses` VALUES (1,'6cbc1427-5feb-11f1-b3c8-005056c00001','040000000','042100000','042103000','042103046',NULL),(2,'4620ed6a-6afb-41d7-83a5-caeab4931daf','010000000','012800000','012812000','012812056',NULL),(3,'18ce28cf-5255-4d61-96cc-f9fbf559d68a','150000000','150700000','150709000','150709001',NULL),(8,'094fbd21-0396-4b12-a0d9-23c9ddc5ed12','040000000','042100000','042103000','042103004',NULL);
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
INSERT INTO `users` VALUES ('094fbd21-0396-4b12-a0d9-23c9ddc5ed12','pnpbetainvestigator','SecurePass123!','user@gmail.com','Beta','Investigator',NULL,NULL,'+639012938409',NULL,'Male','2008-06-03',4,'police',NULL,'deactivated',NULL,0,NULL,NULL,'2026-06-04 22:34:00','2026-06-04 22:47:41',NULL,NULL,0,NULL,2,NULL),('18ce28cf-5255-4d61-96cc-f9fbf559d68a','pnpcharliepatrol','SecurePass123!','ilaciojairusmiguel@gmail.com','Charlie','Patrol',NULL,NULL,'+639021934091',NULL,'Male','2008-06-03',3,'police',NULL,'verified',NULL,0,'2026-06-04 22:48:06',NULL,'2026-06-04 16:28:27','2026-06-04 22:48:06',NULL,NULL,0,NULL,1,NULL),('4620ed6a-6afb-41d7-83a5-caeab4931daf','pnpbetapatrol','SecurePass123!','ilaciojairus@gmail.com','Beta','Patrol',NULL,NULL,'+639023498109',NULL,'Male','2008-06-03',3,'police',NULL,'verified',NULL,0,NULL,NULL,'2026-06-04 16:06:37','2026-06-04 19:05:51',NULL,NULL,0,NULL,1,NULL),('6cbc1427-5feb-11f1-b3c8-005056c00001','II26010_pnp','SecurePass1234!','jairus.oicali@gmail.com','Juan','Dela Cruz','Santos',NULL,'+639171234567',NULL,'Male','2003-10-05',1,'police','/uploads/profiles/6cbc1427-5feb-11f1-b3c8-005056c00001_a5d499f6d28048788e500227f5a47895.png','verified',NULL,0,'2026-06-05 11:00:57',NULL,'2026-06-04 16:00:17','2026-06-05 11:00:57',NULL,NULL,0,NULL,NULL,NULL);
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trigger_auto_add_patroller` AFTER INSERT ON `users` FOR EACH ROW BEGIN
    IF NEW.role_id = 3 THEN
        INSERT IGNORE INTO active_patroller (officer_id)
        VALUES (NEW.user_id);
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `update_users_updated_at` BEFORE UPDATE ON `users` FOR EACH ROW BEGIN
    SET NEW.`updated_at` = CURRENT_TIMESTAMP;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `trigger_auto_update_patroller_role` AFTER UPDATE ON `users` FOR EACH ROW BEGIN
    IF OLD.role_id != NEW.role_id THEN

        IF NEW.role_id = 3 THEN
            INSERT IGNORE INTO active_patroller (officer_id)
            VALUES (NEW.user_id);

        ELSEIF OLD.role_id = 3 AND NEW.role_id != 3 THEN
            DELETE FROM active_patroller
            WHERE officer_id = NEW.user_id;

        END IF;

    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Dumping routines for database 'bantay'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-05 12:54:33
