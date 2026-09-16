-- Schema-only mirror of the 6 flokiq-sandbox tables farmer_chat's voice
-- pipeline actually touches, extracted from flokiq_new.sql (phpMyAdmin
-- dump, 2026-05-06) and cross-checked against the live sandbox
-- (~/flokiq_only_schema.md, generated via SHOW TABLES + DESCRIBE).
--
-- STRUCTURE ONLY. Zero rows of real data — this file must never contain
-- an actual farmer/appointment/health record. Load this into a disposable
-- local MySQL/MariaDB container to test INSERT/UPSERT payload shapes and
-- constraint behavior (species enum, doctorId/addedByUserId FKs) before
-- anything touches the real sandbox. See scripts/flokiq_mock_server.py.
--
-- Dependency order: users -> farmers -> farms -> animals -> health_logs
-- -> appointments. Two FK targets from the real schema are intentionally
-- omitted here (`stores`, `animal_groups`) because the columns that
-- reference them (farmers.storeId, animals.group_id) are nullable and
-- unused by farmer_chat's write path — the mirror just never sets them.

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `appointments`;
DROP TABLE IF EXISTS `health_logs`;
DROP TABLE IF EXISTS `animals`;
DROP TABLE IF EXISTS `farms`;
DROP TABLE IF EXISTS `farmers`;
DROP TABLE IF EXISTS `users`;

CREATE TABLE `users` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `firstName` varchar(255) DEFAULT NULL,
  `middleName` varchar(255) DEFAULT NULL,
  `lastName` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(255) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `role` enum('admin','agent','farmer','storeAdmin','storeManager') DEFAULT NULL,
  `profileImage` varchar(255) DEFAULT NULL,
  `permissions` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`permissions`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `app_permissions` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`app_permissions`)),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `farmers` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `aadharNo` varchar(255) DEFAULT NULL,
  `aadharPhoto` varchar(255) DEFAULT NULL,
  `gender` varchar(255) DEFAULT NULL,
  `fatherOrSpouseName` varchar(255) DEFAULT NULL,
  `alternateMobile` varchar(255) DEFAULT NULL,
  `address_1` varchar(255) DEFAULT NULL,
  `address_2` varchar(255) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `state` varchar(255) DEFAULT NULL,
  `pincode` varchar(255) DEFAULT NULL,
  `country` varchar(255) DEFAULT NULL,
  `hasPanCard` varchar(255) DEFAULT NULL,
  `panNo` varchar(255) DEFAULT NULL,
  `dob` datetime DEFAULT NULL,
  `religion` varchar(255) DEFAULT NULL,
  `caste` varchar(255) DEFAULT NULL,
  `education` varchar(255) DEFAULT NULL,
  `otherEducation` varchar(255) DEFAULT NULL,
  `occupation` varchar(255) DEFAULT NULL,
  `otherOccupation` varchar(255) DEFAULT NULL,
  `farmingExperience` varchar(255) DEFAULT NULL,
  `landHolding` float DEFAULT NULL,
  `organizations` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`organizations`)),
  `otherOrganizations` varchar(255) DEFAULT NULL,
  `hasGovernmentId` varchar(255) DEFAULT NULL,
  `governmentIdPhoto` varchar(255) DEFAULT NULL,
  `isAadharVerified` tinyint(1) DEFAULT NULL,
  `isPanVerified` tinyint(1) DEFAULT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `panVerifiedData` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`panVerifiedData`)),
  `boardingDetails` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`boardingDetails`)),
  `flokiqId` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `onboardedBy` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'User who onboarded this farmer',
  `latitude` decimal(10,7) DEFAULT NULL,
  `longitude` decimal(10,7) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `userId` (`userId`),
  KEY `farmers_onboardedBy_foreign_idx` (`onboardedBy`),
  CONSTRAINT `farmers_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`) ON UPDATE CASCADE,
  CONSTRAINT `farmers_onboardedBy_foreign_idx` FOREIGN KEY (`onboardedBy`) REFERENCES `users` (`id`)
  -- omitted: farmers_ibfk_3 FK (storeId) REFERENCES stores(id) — storeId is nullable, stores table not mirrored
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `farms` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(255) NOT NULL,
  `alternatePhone` varchar(255) DEFAULT NULL,
  `address` text DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `district` varchar(255) DEFAULT NULL,
  `pincode` int(11) DEFAULT NULL,
  `state` varchar(255) DEFAULT NULL,
  `country` varchar(255) DEFAULT 'India',
  `totalAnimalCapacity` int(11) DEFAULT NULL COMMENT 'Maximum animal capacity',
  `currentAnimalCount` int(11) DEFAULT 0,
  `sheepCount` int(11) DEFAULT 0,
  `goatCount` int(11) DEFAULT 0,
  `image` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Primary farm images' CHECK (json_valid(`image`)),
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `farmerId` (`farmerId`),
  CONSTRAINT `farms_ibfk_1` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `animals` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `unique_animal_id` varchar(255) NOT NULL COMMENT 'Primary identifier - can be sequential or include year of birth. Critical for traceability.',
  `species` enum('sheep','goat') NOT NULL COMMENT 'Differentiates between sheep and goat records -- NOTE: no cow/buffalo/chicken value exists',
  `breed` varchar(255) DEFAULT NULL,
  `sex` enum('male','female') NOT NULL,
  `birth_date` date DEFAULT NULL,
  `age_months` int(11) DEFAULT NULL,
  `sire_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `dam_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `current_location` varchar(255) DEFAULT NULL,
  `group_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `status` enum('active','sold','deceased','culled','pregnant','sick') NOT NULL DEFAULT 'active',
  `photos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`photos`)),
  `video` varchar(255) DEFAULT NULL,
  `acquisition_date` date DEFAULT NULL,
  `acquisition_source` varchar(255) DEFAULT NULL,
  `premises_id` varchar(255) DEFAULT NULL,
  `official_tag_type` enum('visual','rfid','tattoo','microchip') DEFAULT NULL,
  `official_tag_number` varchar(255) DEFAULT NULL,
  `color` varchar(255) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `initial_weight_kg` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_animal_id` (`unique_animal_id`),
  UNIQUE KEY `official_tag_number` (`official_tag_number`),
  KEY `farmId` (`farmId`),
  KEY `sire_id` (`sire_id`),
  KEY `dam_id` (`dam_id`),
  CONSTRAINT `animals_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`),
  CONSTRAINT `animals_ibfk_2` FOREIGN KEY (`sire_id`) REFERENCES `animals` (`id`),
  CONSTRAINT `animals_ibfk_3` FOREIGN KEY (`dam_id`) REFERENCES `animals` (`id`)
  -- omitted: animals_ibfk_4 FK (group_id) REFERENCES animal_groups(id) — nullable, animal_groups not mirrored
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `health_logs` (
  `log_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `user_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `pincode` varchar(255) NOT NULL,
  `symptoms_reported` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Array of symptom strings' CHECK (json_valid(`symptoms_reported`)),
  `ai_diagnosis_suggestion` text DEFAULT NULL,
  `potential_ailments` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`potential_ailments`)),
  `first_aid_advice` text DEFAULT NULL,
  `risk_level` enum('Low','Medium','High') DEFAULT NULL,
  `log_timestamp` datetime NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  PRIMARY KEY (`log_id`),
  KEY `user_id` (`user_id`),
  KEY `animal_id` (`animal_id`),
  CONSTRAINT `health_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `health_logs_ibfk_2` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `appointments` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `date` date NOT NULL,
  `time` varchar(255) NOT NULL,
  `status` enum('pending','completed','cancelled','confirmed','missed') NOT NULL DEFAULT 'pending',
  `addedByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `doctorId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `healthLogId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Reference to health log for context when scheduling from symptom checker',
  PRIMARY KEY (`id`),
  KEY `farmerId` (`farmerId`),
  KEY `addedByUserId` (`addedByUserId`),
  KEY `doctorId` (`doctorId`),
  KEY `appointments_healthLogId_foreign_idx` (`healthLogId`),
  CONSTRAINT `appointments_healthLogId_foreign_idx` FOREIGN KEY (`healthLogId`) REFERENCES `health_logs` (`log_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `appointments_ibfk_1` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`),
  CONSTRAINT `appointments_ibfk_2` FOREIGN KEY (`addedByUserId`) REFERENCES `users` (`id`),
  CONSTRAINT `appointments_ibfk_3` FOREIGN KEY (`doctorId`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

SET FOREIGN_KEY_CHECKS = 1;
