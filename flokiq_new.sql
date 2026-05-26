-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: May 06, 2026 at 09:23 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.0.30

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `flokiq_new1`
--

-- --------------------------------------------------------

--
-- Table structure for table `agentroles`
--

CREATE TABLE `agentroles` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `agents`
--

CREATE TABLE `agents` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `roleId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `gender` varchar(255) DEFAULT NULL,
  `dob` datetime DEFAULT NULL,
  `alternatePhone` varchar(255) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `state` varchar(255) DEFAULT NULL,
  `pincode` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `agent_location_history`
--

CREATE TABLE `agent_location_history` (
  `id` int(11) NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `latitude` decimal(10,7) NOT NULL,
  `longitude` decimal(10,7) NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `alerts`
--

CREATE TABLE `alerts` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `type` varchar(255) NOT NULL,
  `title` varchar(255) NOT NULL,
  `message` text DEFAULT NULL,
  `metaData` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`metaData`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animals`
--

CREATE TABLE `animals` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `unique_animal_id` varchar(255) NOT NULL COMMENT 'Primary identifier - can be sequential or include year of birth. Critical for traceability.',
  `species` enum('sheep','goat') NOT NULL COMMENT 'Differentiates between sheep and goat records',
  `breed` varchar(255) DEFAULT NULL COMMENT 'Specific breed (e.g., Jamunapari, Jakharana for goats). Important for performance tracking.',
  `sex` enum('male','female') NOT NULL COMMENT 'Sex of the animal',
  `birth_date` date DEFAULT NULL COMMENT 'Crucial for age-based management and growth tracking',
  `age_months` int(11) DEFAULT NULL COMMENT 'Calculated age in months',
  `sire_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Father ID - vital for genetic lineage and preventing inbreeding',
  `dam_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Mother ID - vital for genetic lineage and preventing inbreeding',
  `current_location` varchar(255) DEFAULT NULL COMMENT 'Current paddock/location. Essential for grazing management and group monitoring.',
  `group_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `status` enum('active','sold','deceased','culled','pregnant','sick') NOT NULL DEFAULT 'active' COMMENT 'Current status for accurate inventory management and disposition records',
  `photos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Array of photo URLs for visual identification and documenting unique characteristics' CHECK (json_valid(`photos`)),
  `video` varchar(255) DEFAULT NULL COMMENT 'Video URL for additional documentation',
  `acquisition_date` date DEFAULT NULL COMMENT 'Date of acquisition - provides initial traceability',
  `acquisition_source` varchar(255) DEFAULT NULL COMMENT 'Source of acquisition - supports financial records and traceability',
  `premises_id` varchar(255) DEFAULT NULL COMMENT 'PIN/LID - Links animals to their farm of origin for regulatory compliance (India/US)',
  `official_tag_type` enum('visual','rfid','tattoo','microchip') DEFAULT NULL COMMENT 'Type of official identification used (e.g., ear tag, RFID, microchip)',
  `official_tag_number` varchar(255) DEFAULT NULL COMMENT 'The specific number on the official identification tag',
  `color` varchar(255) DEFAULT NULL COMMENT 'Physical color/markings description',
  `notes` text DEFAULT NULL COMMENT 'Additional notes and observations',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `initial_weight_kg` float DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animals_health_records`
--

CREATE TABLE `animals_health_records` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Animal this health record belongs to',
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Farm where the animal is located',
  `health_status` enum('healthy','sick','injured') NOT NULL DEFAULT 'healthy' COMMENT 'Quick overview of current health condition',
  `date_of_event` date NOT NULL COMMENT 'Date the health event occurred',
  `event_type` enum('vaccination','treatment','symptom','hoof_care','parasite_control','vet_visit','quarantine') NOT NULL COMMENT 'Categorization of the health activity',
  `vaccine_type` varchar(255) DEFAULT NULL COMMENT 'Specific vaccine administered (e.g., FMD, Brucellosis)',
  `medication` varchar(255) DEFAULT NULL COMMENT 'Name of medication or treatment given',
  `dosage` varchar(255) DEFAULT NULL COMMENT 'Amount of medication administered (e.g., "10ml", "2 tablets")',
  `reason_for_treatment` text DEFAULT NULL COMMENT 'Why the treatment was given (e.g., specific disease, injury)',
  `administered_by` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Person or veterinarian who administered the treatment',
  `withdrawal_period_end_date` date DEFAULT NULL COMMENT 'Date until which animal products cannot be consumed/sold after treatment',
  `symptoms_observed` text DEFAULT NULL COMMENT 'Specific signs of illness (e.g., diarrhea, lameness, loss of appetite)',
  `diagnosis` text DEFAULT NULL COMMENT 'Identified health issue or disease',
  `hoof_care_date` date DEFAULT NULL COMMENT 'Date of hoof trimming or inspection',
  `hoof_health_notes` text DEFAULT NULL COMMENT 'Observations on hoof condition (e.g., cracks, abscesses)',
  `deworming_date` date DEFAULT NULL COMMENT 'Date of deworming',
  `dewormer_type` varchar(255) DEFAULT NULL COMMENT 'Type of deworming medication used',
  `fecal_egg_count_result` int(11) DEFAULT NULL COMMENT 'Results of parasite load testing (FEC)',
  `quarantine_start_date` date DEFAULT NULL COMMENT 'Start date for isolation of new or sick animals',
  `quarantine_end_date` date DEFAULT NULL COMMENT 'End date for quarantine period',
  `vet_visit_notes` text DEFAULT NULL COMMENT 'Details from veterinarian''s assessment',
  `comments` text DEFAULT NULL COMMENT 'Any additional notes or observations',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animal_groups`
--

CREATE TABLE `animal_groups` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Farm that owns this group',
  `group_name` varchar(255) NOT NULL COMMENT 'Name of the animal group',
  `group_code` varchar(255) DEFAULT NULL COMMENT 'Unique code for the group (e.g., BR-2024-01)',
  `species` enum('sheep','goat','mixed') DEFAULT NULL COMMENT 'Species in this group (can be mixed)',
  `description` text DEFAULT NULL COMMENT 'Detailed description of the group purpose and management',
  `status` enum('active','inactive','archived') NOT NULL DEFAULT 'active' COMMENT 'Current status of the group',
  `color_code` varchar(7) DEFAULT NULL COMMENT 'Hex color code for UI display (e.g., #FF5733)',
  `notes` text DEFAULT NULL COMMENT 'General notes about the group',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `group_type` enum('static','dynamic') NOT NULL DEFAULT 'static'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animal_group_actions`
--

CREATE TABLE `animal_group_actions` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `groupId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `action_type` enum('vaccination','movement','feed','treatment') NOT NULL,
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`payload`)),
  `createdAt` datetime DEFAULT NULL,
  `updatedAt` datetime DEFAULT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animal_group_rules`
--

CREATE TABLE `animal_group_rules` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `groupId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `rules` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`rules`)),
  `createdAt` datetime DEFAULT NULL,
  `updatedAt` datetime DEFAULT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animal_group_species`
--

CREATE TABLE `animal_group_species` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `groupId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animalId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `createdAt` datetime DEFAULT NULL,
  `updatedAt` datetime DEFAULT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `animal_movements`
--

CREATE TABLE `animal_movements` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `date_of_movement` date NOT NULL COMMENT 'Date the animal moved',
  `origin_location` varchar(255) NOT NULL COMMENT 'Where the animal moved from (e.g., paddock, farm)',
  `destination_location` varchar(255) NOT NULL COMMENT 'Where the animal moved to (e.g., new farm, slaughterhouse)',
  `reason_for_movement` enum('Sale','Transfer','Slaughter','Exhibition','Breeding','Veterinary Treatment','Other') NOT NULL COMMENT 'Purpose of the movement',
  `buyer_name` varchar(255) DEFAULT NULL,
  `buyer_address` text DEFAULT NULL,
  `seller_name` varchar(255) DEFAULT NULL,
  `seller_address` text DEFAULT NULL,
  `official_identification_status` tinyint(1) DEFAULT NULL COMMENT 'Whether animal has required official ID',
  `premises_registration_status` tinyint(1) DEFAULT NULL COMMENT 'Whether the premises are officially registered',
  `disease_reporting_date` date DEFAULT NULL COMMENT 'Date disease was reported to authorities',
  `disease_reported` varchar(255) DEFAULT NULL COMMENT 'Name of the disease reported',
  `authority_reported_to` varchar(255) DEFAULT NULL COMMENT 'Regulatory body to which the disease was reported',
  `slaughterhouse_name` varchar(255) DEFAULT NULL,
  `slaughterhouse_address` text DEFAULT NULL,
  `slaughterhouse_registration_number` varchar(255) DEFAULT NULL,
  `transport_method` enum('Truck','Rail','Air','Ship','Walking','Other') DEFAULT NULL,
  `transported_by` varchar(255) DEFAULT NULL COMMENT 'Name of transporter/company',
  `distance_km` decimal(10,2) DEFAULT NULL,
  `number_of_animals` int(11) NOT NULL DEFAULT 1 COMMENT 'Number of animals in this movement',
  `veterinary_inspection_date` date DEFAULT NULL,
  `veterinary_inspector_name` varchar(255) DEFAULT NULL,
  `movement_permit_number` varchar(255) DEFAULT NULL,
  `export_import_permit_number` varchar(255) DEFAULT NULL,
  `health_certificate_number` varchar(255) DEFAULT NULL,
  `movement_status` enum('Planned','In Transit','Completed','Cancelled') NOT NULL DEFAULT 'Planned',
  `comments` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `answers`
--

CREATE TABLE `answers` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `categoryId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `questionId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `selectedOptions` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`selectedOptions`)),
  `inputValue` varchar(255) DEFAULT NULL COMMENT 'Stores input values for input-type questions',
  `comment` text DEFAULT NULL,
  `question` varchar(255) NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `appointments`
--

CREATE TABLE `appointments` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `date` date NOT NULL,
  `time` varchar(255) NOT NULL,
  `status` enum('pending','completed','cancelled','confirmed','missed') NOT NULL DEFAULT 'pending' COMMENT 'Appointment status',
  `addedByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `doctorId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `healthLogId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Reference to health log for context when scheduling from symptom checker'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `birth_events`
--

CREATE TABLE `birth_events` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `breeding_event_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Reference to the breeding event that resulted in this birth',
  `dam_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Dam (mother) who gave birth',
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Farm where birth occurred',
  `actual_kidding_date` date NOT NULL COMMENT 'Actual date of birth event (kidding/lambing)',
  `number_of_offspring` int(11) NOT NULL COMMENT 'Litter size (e.g., 1=single, 2=twins, 3=triplets)',
  `kidding_ease` enum('easy','normal','difficult','assisted','cesarean') DEFAULT NULL COMMENT 'Assessment of the difficulty of the birth',
  `mothering_ability` enum('excellent','good','fair','poor','rejected') DEFAULT NULL COMMENT 'Assessment of the dam''s care for offspring',
  `comments` text DEFAULT NULL COMMENT 'Any additional notes on the birth event',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `breeding_events`
--

CREATE TABLE `breeding_events` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `dam_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Dam (female parent) of this breeding event',
  `sire_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Sire (male parent) of this breeding event',
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Farm where breeding occurred',
  `breeding_date` date NOT NULL COMMENT 'Date of breeding event',
  `breeding_method` enum('natural','ai','et') NOT NULL DEFAULT 'natural' COMMENT 'Method used for breeding (Natural, AI=Artificial Insemination, ET=Embryo Transfer)',
  `pregnancy_status` enum('open','bred','confirmed_pregnant','aborted','kidded_lambed') NOT NULL DEFAULT 'bred' COMMENT 'Current reproductive status',
  `pregnancy_confirmation_date` date DEFAULT NULL COMMENT 'Date pregnancy was confirmed (e.g., by palpation, ultrasound)',
  `expected_kidding_date` date DEFAULT NULL COMMENT 'Predicted birth date (auto-calculated based on breeding date and gestation period)',
  `breeding_suitability_age` int(11) DEFAULT NULL COMMENT 'Age of dam at breeding (in months)',
  `breeding_suitability_weight` decimal(5,2) DEFAULT NULL COMMENT 'Weight of dam at breeding (in kg)',
  `breeding_suitability_bcs` decimal(2,1) DEFAULT NULL COMMENT 'Body Condition Score at breeding (1-5 scale)',
  `comments` text DEFAULT NULL COMMENT 'Any additional notes on the breeding event',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `categories`
--

CREATE TABLE `categories` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) NOT NULL,
  `slug` varchar(255) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `image` varchar(255) DEFAULT NULL,
  `position` int(11) NOT NULL DEFAULT 1,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `farmers`
--

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
  `longitude` decimal(10,7) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `farms`
--

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
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `farm_diseases`
--

CREATE TABLE `farm_diseases` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `diseases` varchar(255) NOT NULL,
  `image` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`image`)),
  `createdAt` datetime DEFAULT current_timestamp(),
  `updatedAt` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `farm_images`
--

CREATE TABLE `farm_images` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `type` enum('farm','animal') NOT NULL,
  `image` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`image`)),
  `createdAt` datetime DEFAULT current_timestamp(),
  `updatedAt` datetime DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `feed_nutritions`
--

CREATE TABLE `feed_nutritions` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `feed_date` date DEFAULT NULL COMMENT 'Date feed was provided',
  `feed_type` enum('Hay','Grain','Silage','Supplement','Other') DEFAULT NULL COMMENT 'Type of feed given',
  `feed_quantity` float DEFAULT NULL COMMENT 'Amount of feed consumed per animal or group',
  `feeding_schedule` varchar(255) DEFAULT NULL COMMENT 'Regularity or timing of feeding',
  `fodder_availability` int(11) DEFAULT NULL COMMENT 'Current stock level of feed (kg, tons, or bags)',
  `fodder_cost` float DEFAULT NULL COMMENT 'Cost associated with feed purchase or production',
  `grazing_paddock` varchar(255) DEFAULT NULL COMMENT 'Pasture or area where animals are grazing',
  `grazing_start_date` date DEFAULT NULL COMMENT 'Date animals began grazing in a specific paddock',
  `grazing_end_date` date DEFAULT NULL COMMENT 'Date animals finished grazing in a specific paddock',
  `number_of_animals_grazing` int(11) DEFAULT NULL COMMENT 'Count of animals grazing in this paddock',
  `comments` text DEFAULT NULL COMMENT 'Additional notes on feeding or grazing',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `financial_transactions`
--

CREATE TABLE `financial_transactions` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `recorded_by` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `transaction_date` datetime NOT NULL COMMENT 'Date when the transaction occurred',
  `transaction_type` enum('Income','Expense') NOT NULL,
  `category` enum('Animal Sale','Milk Sale','Wool Sale','Other Income','Feed Cost','Vet Expenses','Labor','Equipment','Breeding Expenses','Utilities','Maintenance','Other Expense') NOT NULL,
  `sub_category` varchar(100) DEFAULT NULL COMMENT 'Further breakdown of category (e.g., Medical Expenses, Breeding Expenses)',
  `description` text DEFAULT NULL COMMENT 'Description of the transaction',
  `amount` decimal(12,2) NOT NULL COMMENT 'Total monetary value of the transaction',
  `quantity` decimal(10,2) DEFAULT NULL COMMENT 'Number of animals or units of product (for sales)',
  `unit_price` decimal(10,2) DEFAULT NULL COMMENT 'Price per animal or unit of product (for sales)',
  `buyer_details` text DEFAULT NULL COMMENT 'Information about the buyer (for income transactions)',
  `seller_details` text DEFAULT NULL COMMENT 'Information about the seller (for expense transactions)',
  `payment_method` enum('cash','bank_transfer','card','check','other') NOT NULL DEFAULT 'cash',
  `payment_status` enum('pending','completed','failed','refunded') NOT NULL DEFAULT 'completed',
  `reference_number` varchar(100) DEFAULT NULL COMMENT 'Transaction reference or receipt number',
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Reference to animal if transaction is related to specific animal',
  `comments` text DEFAULT NULL COMMENT 'Any additional notes on the financial transaction',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `goods_receipts`
--

CREATE TABLE `goods_receipts` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique identifier for goods receipt (GRN)',
  `grnNumber` varchar(255) NOT NULL COMMENT 'System generated GRN number',
  `purchaseOrderId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Reference to purchase order',
  `vendorId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Vendor from whom goods were received',
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Store / pharmacy where stock is received',
  `receivedDate` date NOT NULL COMMENT 'Date when goods were physically received',
  `receivedBy` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'User who received the goods',
  `status` enum('PARTIALLY_RECEIVED','FULLY_RECEIVED','REJECTED') NOT NULL DEFAULT 'FULLY_RECEIVED' COMMENT 'Goods receipt status',
  `remarks` text DEFAULT NULL COMMENT 'Shortage / damage / quality remarks',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `health_logs`
--

CREATE TABLE `health_logs` (
  `log_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `user_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `pincode` varchar(255) NOT NULL,
  `symptoms_reported` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Array of symptom strings' CHECK (json_valid(`symptoms_reported`)),
  `ai_diagnosis_suggestion` text DEFAULT NULL COMMENT 'AI-generated diagnosis suggestion',
  `potential_ailments` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Array of potential diseases/ailments' CHECK (json_valid(`potential_ailments`)),
  `first_aid_advice` text DEFAULT NULL COMMENT 'First aid recommendations',
  `risk_level` enum('Low','Medium','High') DEFAULT NULL COMMENT 'Risk level assessment',
  `log_timestamp` datetime NOT NULL COMMENT 'Timestamp when the log was created',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `inventory`
--

CREATE TABLE `inventory` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `quantity` int(11) NOT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `inventory_batches`
--

CREATE TABLE `inventory_batches` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique identifier for inventory batch record',
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Store where this batch is stored',
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Product to which this batch belongs',
  `batchNumber` varchar(255) NOT NULL COMMENT 'Manufacturer batch number printed on the product',
  `expiryDate` date NOT NULL COMMENT 'Expiry date of the batch for FEFO and compliance',
  `quantityReceived` int(11) NOT NULL COMMENT 'Total quantity received in this batch',
  `quantityAvailable` int(11) NOT NULL COMMENT 'Current available quantity in this batch',
  `quantityReserved` int(11) NOT NULL DEFAULT 0 COMMENT 'Quantity reserved for pending sales or transfers',
  `costPrice` float DEFAULT NULL COMMENT 'Cost price per unit for this batch',
  `physicalLocation` varchar(255) DEFAULT NULL COMMENT 'Physical storage location (e.g., Rack A-3, Refrigerator 1)',
  `status` enum('Quarantine','Available','NearExpiry','Expired','Recalled') NOT NULL DEFAULT 'Quarantine' COMMENT 'Current status of the batch for safety and compliance',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `inventory_history`
--

CREATE TABLE `inventory_history` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `type` enum('in','out','transfer') NOT NULL COMMENT 'Stock In or Stock Out',
  `quantity` int(11) NOT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `listings`
--

CREATE TABLE `listings` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `seller_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `expected_price` int(11) NOT NULL,
  `listing_status` enum('active','sold','inactive') DEFAULT 'active',
  `mediaurl` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `notifications`
--

CREATE TABLE `notifications` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `message` text NOT NULL,
  `farmers` enum('ALL','FLOKIQ','KSWDCL','NOT_KSWDCL') NOT NULL,
  `totalRecipients` int(11) DEFAULT 0,
  `successCount` int(11) DEFAULT 0,
  `failedCount` int(11) DEFAULT 0,
  `status` enum('success','partial','failed') DEFAULT NULL,
  `createdAt` datetime NOT NULL DEFAULT current_timestamp(),
  `updatedAt` datetime NOT NULL DEFAULT current_timestamp(),
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `offspring_records`
--

CREATE TABLE `offspring_records` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `birth_event_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Reference to the birth event',
  `offspring_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique ID of the offspring animal',
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Farm where offspring was born',
  `gender` enum('male','female') NOT NULL COMMENT 'Gender of the offspring',
  `birth_weight` decimal(5,2) DEFAULT NULL COMMENT 'Weight of offspring at birth (in kg)',
  `birth_order` int(11) DEFAULT NULL COMMENT 'Order of birth in multiple births (1st, 2nd, 3rd, etc.)',
  `survival_status` enum('alive','stillborn','died_within_24h','died_within_7d') NOT NULL DEFAULT 'alive' COMMENT 'Survival status of the offspring',
  `comments` text DEFAULT NULL COMMENT 'Any additional notes about this offspring',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `orders`
--

CREATE TABLE `orders` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `orderCode` varchar(255) DEFAULT NULL,
  `addedByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `quantity` int(11) DEFAULT NULL,
  `totalAmount` float DEFAULT NULL,
  `status` enum('processing','shipped','delivered','cancelled') NOT NULL DEFAULT 'processing' COMMENT 'Order status',
  `deliveryAddress` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `paymentMethod` varchar(255) DEFAULT NULL COMMENT 'Payment method used for the order (cash, card, upi)',
  `cardName` varchar(255) DEFAULT NULL COMMENT 'Card name or bank name if payment method is card',
  `transactionId` varchar(255) DEFAULT NULL COMMENT 'Transaction reference ID for UPI or card payments',
  `upiName` varchar(255) DEFAULT NULL COMMENT 'UPI app or account name used for payment',
  `paymentStatus` enum('pending','created','paid','failed') NOT NULL DEFAULT 'pending',
  `razorpayOrderId` varchar(255) DEFAULT NULL,
  `razorpayPaymentId` varchar(255) DEFAULT NULL,
  `currency` varchar(255) DEFAULT 'INR'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `orders_items`
--

CREATE TABLE `orders_items` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmerId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `quantity` int(11) DEFAULT NULL,
  `price` float DEFAULT NULL,
  `discount` float DEFAULT NULL,
  `tax` float DEFAULT NULL,
  `subtotal` float DEFAULT NULL,
  `total` float DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `orderId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `otpverifications`
--

CREATE TABLE `otpverifications` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `otp` int(11) DEFAULT NULL,
  `notes` varchar(255) NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `productcategories`
--

CREATE TABLE `productcategories` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) NOT NULL,
  `slug` varchar(255) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `image` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `production_performance`
--

CREATE TABLE `production_performance` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farm_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animal_id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `date_of_measurement` date NOT NULL,
  `weight` float DEFAULT NULL,
  `weight_type` enum('Birth','Weaning','Monthly','Sale') DEFAULT NULL,
  `milk_production_daily_yield` float DEFAULT NULL,
  `wool_production_weight` float DEFAULT NULL,
  `wool_quality_micron_count` float DEFAULT NULL,
  `body_condition_score` float DEFAULT NULL,
  `meat_yield_carcass_weight` float DEFAULT NULL,
  `dressing_percentage` float DEFAULT NULL,
  `recorded_by` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `comments` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `products`
--

CREATE TABLE `products` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `productCategoryId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `productSubCategoryId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `productName` varchar(255) NOT NULL,
  `companyName` varchar(255) NOT NULL,
  `packType` varchar(255) NOT NULL,
  `unitOfMeasurement` varchar(255) NOT NULL,
  `productPrice` float NOT NULL,
  `tax` float NOT NULL,
  `availableQuantity` int(11) NOT NULL,
  `discount` float NOT NULL,
  `ownProduct` enum('yes','no') NOT NULL,
  `image` varchar(255) NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `addedByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'User who added this product',
  `SKU` varchar(255) DEFAULT NULL COMMENT 'Stock Keeping Unit for internal inventory tracking',
  `UPC_EAN` varchar(255) DEFAULT NULL COMMENT 'Barcode number used for retail scanning (UPC/EAN)',
  `HSN_Code` varchar(255) DEFAULT NULL COMMENT 'HSN code for GST compliance in India',
  `CDSCO_Reg_No` varchar(255) DEFAULT NULL COMMENT 'CDSCO registration number required for legal drug sales in India',
  `genericName` varchar(255) DEFAULT NULL COMMENT 'Generic name of the active pharmaceutical ingredient',
  `strength` varchar(255) DEFAULT NULL COMMENT 'Strength or concentration of the active ingredient (e.g., 500mg)',
  `form` varchar(255) DEFAULT NULL COMMENT 'Physical form of the product such as Tablet, Injection, or Liquid',
  `isPrescriptionRequired` tinyint(1) DEFAULT 0 COMMENT 'Indicates whether a prescription is mandatory for selling this product',
  `costPrice` float DEFAULT NULL COMMENT 'Purchase cost price from the vendor',
  `maximumRetailPrice_MRP` float DEFAULT NULL COMMENT 'Government-regulated Maximum Retail Price (MRP)',
  `sellingPrice` float DEFAULT NULL COMMENT 'Final selling price offered to the customer',
  `reorderLevel` int(11) DEFAULT NULL COMMENT 'Minimum stock level that triggers a reorder alert',
  `thickness` varchar(255) DEFAULT NULL,
  `logistics` float DEFAULT NULL,
  `margin` float DEFAULT NULL,
  `memberPrice` float DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `productsubcategories`
--

CREATE TABLE `productsubcategories` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `categoryId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) NOT NULL,
  `image` varchar(255) NOT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `product_inventory`
--

CREATE TABLE `product_inventory` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `quantity` int(11) NOT NULL,
  `notes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `purchase_orders`
--

CREATE TABLE `purchase_orders` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique purchase order identifier',
  `vendorId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Vendor supplying the goods',
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Store placing the purchase order',
  `poNumber` varchar(255) NOT NULL,
  `orderDate` date NOT NULL COMMENT 'Purchase order creation date',
  `expectedDeliveryDate` date DEFAULT NULL COMMENT 'Expected delivery date from vendor',
  `paymentTerms` varchar(255) DEFAULT NULL COMMENT 'Payment terms (Net 30, Advance, COD, etc.)',
  `shippingAddress` text DEFAULT NULL COMMENT 'Delivery address for the purchase order',
  `notes` text DEFAULT NULL COMMENT 'Additional notes or instructions',
  `totalAmount` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT 'Total purchase order amount',
  `status` enum('DRAFT','ORDERED','PARTIALLY_RECEIVED','RECEIVED','CANCELLED') NOT NULL DEFAULT 'ORDERED' COMMENT 'Current status of the purchase order',
  `invoiceNumber` varchar(255) DEFAULT NULL COMMENT 'Vendor invoice number',
  `invoiceDate` date DEFAULT NULL COMMENT 'Vendor invoice date',
  `paymentStatus` enum('UNPAID','PARTIAL','PAID') NOT NULL DEFAULT 'UNPAID' COMMENT 'Payment status of the purchase order',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `purchase_order_items`
--

CREATE TABLE `purchase_order_items` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique purchase order item identifier',
  `purchaseOrderId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Parent purchase order',
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Product being purchased',
  `orderedQuantity` int(11) NOT NULL COMMENT 'Quantity ordered in purchase order',
  `receivedQuantity` int(11) NOT NULL DEFAULT 0 COMMENT 'Quantity received so far',
  `unitPrice` decimal(10,2) NOT NULL COMMENT 'Cost price per unit at order time',
  `lineTotal` decimal(12,2) NOT NULL COMMENT 'orderedQuantity × unitPrice',
  `status` enum('OPEN','PARTIALLY_RECEIVED','RECEIVED','CANCELLED') NOT NULL DEFAULT 'OPEN' COMMENT 'Status of this purchase order item',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `questions`
--

CREATE TABLE `questions` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `categoryId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `question` text NOT NULL,
  `placeholder` text NOT NULL,
  `type` enum('input','input-list','group','barcode','select','file','textarea','date','number','email','phone') NOT NULL,
  `options` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`options`)),
  `position` int(11) NOT NULL DEFAULT 1,
  `multiSelect` tinyint(1) NOT NULL DEFAULT 0,
  `parentQuestionId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `conditionalLogic` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'JSON object defining when this question should be shown based on parent question answers' CHECK (json_valid(`conditionalLogic`)),
  `commentBoxConditionalLogic` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'JSON object defining when this question should be shown based on parent question answers' CHECK (json_valid(`commentBoxConditionalLogic`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `sales_pipeline`
--

CREATE TABLE `sales_pipeline` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `buyerName` varchar(100) NOT NULL,
  `buyerPhone` varchar(20) NOT NULL,
  `buyerEmail` varchar(100) DEFAULT NULL,
  `status` enum('initial_contact','negotiation','offer_made','confirmed','lost') NOT NULL DEFAULT 'initial_contact',
  `assignedTo` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'User handling this deal',
  `notes` text DEFAULT NULL,
  `followup_date` datetime DEFAULT NULL,
  `total_amount` float DEFAULT NULL,
  `createdAt` datetime NOT NULL DEFAULT current_timestamp(),
  `updatedAt` datetime NOT NULL DEFAULT current_timestamp(),
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `sales_pipeline_animals`
--

CREATE TABLE `sales_pipeline_animals` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `pipelineId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animalId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `proposed_price` float DEFAULT NULL COMMENT 'Negotiated price for this animal',
  `createdAt` datetime NOT NULL DEFAULT current_timestamp(),
  `updatedAt` datetime NOT NULL DEFAULT current_timestamp(),
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `sale_criteria_filters`
--

CREATE TABLE `sale_criteria_filters` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `farmId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(100) NOT NULL,
  `min_weight_kg` float DEFAULT NULL,
  `min_age_months` int(11) DEFAULT NULL,
  `max_age_months` int(11) DEFAULT NULL,
  `species` varchar(50) DEFAULT NULL,
  `breed` varchar(50) DEFAULT NULL,
  `withdrawal_period_clear` tinyint(1) NOT NULL DEFAULT 1,
  `createdBy` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `createdAt` datetime DEFAULT NULL,
  `updatedAt` datetime DEFAULT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `sequelizemeta`
--

CREATE TABLE `sequelizemeta` (
  `name` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `stock_ledger`
--

CREATE TABLE `stock_ledger` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique identifier for each stock movement record',
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Store where the stock movement occurred',
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Product involved in the stock movement',
  `batchId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Batch reference for batch-level traceability',
  `transactionType` enum('IN','OUT','TRANSFER_IN','TRANSFER_OUT','ADJUSTMENT','EXPIRED','RECALLED') NOT NULL COMMENT 'Type of stock movement',
  `quantity` int(11) NOT NULL COMMENT 'Quantity moved (always positive, direction defined by transactionType)',
  `referenceType` varchar(255) DEFAULT NULL COMMENT 'Source document type (GRN, SALE, TRANSFER, ADJUSTMENT)',
  `referenceId` varchar(255) DEFAULT NULL COMMENT 'Reference document ID for audit trail',
  `notes` text DEFAULT NULL COMMENT 'Additional remarks or reason for stock movement',
  `createdByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'User who performed this stock action',
  `createdAt` datetime NOT NULL COMMENT 'Timestamp when the stock movement was recorded',
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `stores`
--

CREATE TABLE `stores` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `storeTypeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(255) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `district` varchar(255) DEFAULT NULL,
  `pincode` varchar(255) DEFAULT NULL,
  `state` varchar(255) DEFAULT NULL,
  `image` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL,
  `storeCode` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `storetypes`
--

CREATE TABLE `storetypes` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tokens`
--

CREATE TABLE `tokens` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `user` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `token` varchar(255) NOT NULL,
  `blacklisted` tinyint(1) DEFAULT 0,
  `type` enum('refresh','resetPassword','verifyEmail') DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `userdetails`
--

CREATE TABLE `userdetails` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `storeId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `gender` varchar(255) DEFAULT NULL,
  `dob` datetime DEFAULT NULL,
  `alternatePhone` varchar(255) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `state` varchar(255) DEFAULT NULL,
  `pincode` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

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
  `app_permissions` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`app_permissions`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `vaccination_schedule`
--

CREATE TABLE `vaccination_schedule` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `addedByUserId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `animalId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  `appointmentId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `vaccineName` varchar(255) DEFAULT NULL,
  `dueDate` datetime DEFAULT NULL,
  `veterinarianNotes` text DEFAULT NULL,
  `createdAt` datetime NOT NULL DEFAULT current_timestamp(),
  `updatedAt` datetime NOT NULL DEFAULT current_timestamp(),
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `vendors`
--

CREATE TABLE `vendors` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique identifier for the supplier',
  `name` varchar(255) NOT NULL COMMENT 'The legal name of the vendor company',
  `gstin` varchar(255) DEFAULT NULL COMMENT 'Vendor''s GST Identification Number',
  `drugLicenseNo` varchar(255) NOT NULL COMMENT 'Mandatory wholesale drug license number (Form 20B & 21B)',
  `drugLicenseExpiry` datetime DEFAULT NULL COMMENT 'Expiry date for automated compliance alerts',
  `paymentTerms` varchar(255) DEFAULT NULL COMMENT 'Agreed payment terms (e.g., Net 30, Advance)',
  `rating` float DEFAULT NULL COMMENT 'System-calculated score based on KPIs like on-time delivery',
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(255) DEFAULT NULL,
  `address` varchar(255) DEFAULT NULL,
  `createdAt` datetime NOT NULL DEFAULT current_timestamp(),
  `updatedAt` datetime NOT NULL DEFAULT current_timestamp(),
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `vendor_products`
--

CREATE TABLE `vendor_products` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Unique vendor product mapping identifier',
  `vendorId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Vendor supplying this product',
  `productId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Product supplied by vendor',
  `price` decimal(10,2) NOT NULL COMMENT 'Price offered by vendor for this product',
  `status` enum('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE' COMMENT 'Availability status of vendor product',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `deletedAt` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `whatsapp_chat`
--

CREATE TABLE `whatsapp_chat` (
  `id` int(11) NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Associated user ID if available',
  `messageId` varchar(255) NOT NULL COMMENT 'WhatsApp message ID',
  `messageType` enum('text','template','image','audio','video','document','location','contact','sticker','interactive','button','list') NOT NULL DEFAULT 'text' COMMENT 'Type of message',
  `templateName` varchar(255) DEFAULT NULL COMMENT 'WhatsApp template name for template messages',
  `templateLanguage` varchar(255) DEFAULT NULL COMMENT 'Template language code',
  `messageText` text DEFAULT NULL COMMENT 'Text content of the message',
  `mediaUrl` varchar(255) DEFAULT NULL COMMENT 'URL for media files (images, videos, documents)',
  `mediaMimeType` varchar(255) DEFAULT NULL COMMENT 'MIME type of media file',
  `status` enum('sent','delivered','read','failed') NOT NULL DEFAULT 'sent' COMMENT 'Message delivery status',
  `direction` enum('inbound','outbound') NOT NULL COMMENT 'Message direction',
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Additional context data (quoted messages, etc.)' CHECK (json_valid(`context`)),
  `conversationId` varchar(255) DEFAULT NULL COMMENT 'Conversation/thread ID for grouping messages',
  `isRead` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Whether the message has been read',
  `extraData` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Extra data' CHECK (json_valid(`extraData`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `whatsapp_leads`
--

CREATE TABLE `whatsapp_leads` (
  `id` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `wa_id` varchar(255) NOT NULL COMMENT 'WhatsApp ID',
  `profile_name` varchar(255) DEFAULT NULL COMMENT 'User profile name',
  `name` varchar(255) DEFAULT NULL COMMENT 'User name',
  `location` varchar(255) DEFAULT NULL COMMENT 'User location',
  `phone_number` varchar(255) DEFAULT NULL COMMENT 'Phone number',
  `step` varchar(255) DEFAULT NULL COMMENT 'Onboarding step',
  `contact_status` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Contact status',
  `contacted_by` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Contacted by user ID if available',
  `contacted_at` datetime DEFAULT NULL COMMENT 'Contacted at',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL,
  `lang` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `whatsapp_lead_chat`
--

CREATE TABLE `whatsapp_lead_chat` (
  `id` int(11) NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Associated WhatsApp lead ID if available',
  `messageId` varchar(255) NOT NULL COMMENT 'WhatsApp message ID',
  `messageType` enum('text','template','image','audio','video','document','location','contact','sticker','interactive','button','list') NOT NULL DEFAULT 'text' COMMENT 'Type of message',
  `templateName` varchar(255) DEFAULT NULL COMMENT 'WhatsApp template name for template messages',
  `templateLanguage` varchar(255) DEFAULT NULL COMMENT 'Template language code',
  `messageText` text DEFAULT NULL COMMENT 'Text content of the message',
  `mediaUrl` varchar(255) DEFAULT NULL COMMENT 'URL for media files (images, videos, documents)',
  `mediaMimeType` varchar(255) DEFAULT NULL COMMENT 'MIME type of media file',
  `status` enum('sent','delivered','read','failed') NOT NULL DEFAULT 'sent' COMMENT 'Message delivery status',
  `direction` enum('inbound','outbound') NOT NULL COMMENT 'Message direction',
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Additional context data (quoted messages, etc.)' CHECK (json_valid(`context`)),
  `conversationId` varchar(255) DEFAULT NULL COMMENT 'Conversation/thread ID for grouping messages',
  `isRead` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Whether the message has been read',
  `extraData` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Extra data' CHECK (json_valid(`extraData`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `whatsapp_response`
--

CREATE TABLE `whatsapp_response` (
  `id` int(11) NOT NULL,
  `response` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'Response from WhatsApp' CHECK (json_valid(`response`)),
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `whatsapp_sessions`
--

CREATE TABLE `whatsapp_sessions` (
  `id` int(11) NOT NULL,
  `userId` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Associated user ID if available',
  `wa_id` varchar(255) NOT NULL COMMENT 'WhatsApp ID',
  `lang` varchar(255) DEFAULT NULL COMMENT 'User selected language',
  `type` varchar(255) DEFAULT NULL COMMENT 'Session type - appointment or product or feedback',
  `payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Session data and context' CHECK (json_valid(`payload`)),
  `step` varchar(255) DEFAULT NULL COMMENT 'Current conversation step',
  `is_completed` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Whether the session is completed',
  `feedback` varchar(255) DEFAULT NULL COMMENT 'Feedback message',
  `contact_status` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Whether the user has been contacted by team',
  `contacted_by` char(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'User ID who contacted this session',
  `notes` text DEFAULT NULL COMMENT 'Additional notes about the session',
  `createdAt` datetime NOT NULL,
  `updatedAt` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `agentroles`
--
ALTER TABLE `agentroles`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `agents`
--
ALTER TABLE `agents`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`),
  ADD KEY `roleId` (`roleId`),
  ADD KEY `storeId` (`storeId`);

--
-- Indexes for table `agent_location_history`
--
ALTER TABLE `agent_location_history`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`);

--
-- Indexes for table `alerts`
--
ALTER TABLE `alerts`
  ADD PRIMARY KEY (`id`),
  ADD KEY `alerts_user_id` (`userId`);

--
-- Indexes for table `animals`
--
ALTER TABLE `animals`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_animal_id` (`unique_animal_id`),
  ADD UNIQUE KEY `official_tag_number` (`official_tag_number`),
  ADD KEY `farmId` (`farmId`),
  ADD KEY `sire_id` (`sire_id`),
  ADD KEY `dam_id` (`dam_id`),
  ADD KEY `group_id` (`group_id`);

--
-- Indexes for table `animals_health_records`
--
ALTER TABLE `animals_health_records`
  ADD PRIMARY KEY (`id`),
  ADD KEY `animal_id` (`animal_id`),
  ADD KEY `farm_id` (`farm_id`),
  ADD KEY `administered_by` (`administered_by`);

--
-- Indexes for table `animal_groups`
--
ALTER TABLE `animal_groups`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `group_code` (`group_code`),
  ADD KEY `farmId` (`farmId`);

--
-- Indexes for table `animal_group_actions`
--
ALTER TABLE `animal_group_actions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `groupId` (`groupId`);

--
-- Indexes for table `animal_group_rules`
--
ALTER TABLE `animal_group_rules`
  ADD PRIMARY KEY (`id`),
  ADD KEY `groupId` (`groupId`);

--
-- Indexes for table `animal_group_species`
--
ALTER TABLE `animal_group_species`
  ADD PRIMARY KEY (`id`),
  ADD KEY `groupId` (`groupId`);

--
-- Indexes for table `animal_movements`
--
ALTER TABLE `animal_movements`
  ADD PRIMARY KEY (`id`),
  ADD KEY `animal_id` (`animal_id`);

--
-- Indexes for table `answers`
--
ALTER TABLE `answers`
  ADD PRIMARY KEY (`id`),
  ADD KEY `categoryId` (`categoryId`),
  ADD KEY `farmerId` (`farmerId`),
  ADD KEY `questionId` (`questionId`);

--
-- Indexes for table `appointments`
--
ALTER TABLE `appointments`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmerId` (`farmerId`),
  ADD KEY `addedByUserId` (`addedByUserId`),
  ADD KEY `doctorId` (`doctorId`),
  ADD KEY `appointments_healthLogId_foreign_idx` (`healthLogId`);

--
-- Indexes for table `birth_events`
--
ALTER TABLE `birth_events`
  ADD PRIMARY KEY (`id`),
  ADD KEY `breeding_event_id` (`breeding_event_id`),
  ADD KEY `dam_id` (`dam_id`),
  ADD KEY `farm_id` (`farm_id`);

--
-- Indexes for table `breeding_events`
--
ALTER TABLE `breeding_events`
  ADD PRIMARY KEY (`id`),
  ADD KEY `dam_id` (`dam_id`),
  ADD KEY `sire_id` (`sire_id`),
  ADD KEY `farm_id` (`farm_id`);

--
-- Indexes for table `categories`
--
ALTER TABLE `categories`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `farmers`
--
ALTER TABLE `farmers`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `farmers_onboardedBy_foreign_idx` (`onboardedBy`);

--
-- Indexes for table `farms`
--
ALTER TABLE `farms`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmerId` (`farmerId`);

--
-- Indexes for table `farm_diseases`
--
ALTER TABLE `farm_diseases`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmId` (`farmId`);

--
-- Indexes for table `farm_images`
--
ALTER TABLE `farm_images`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmId` (`farmId`);

--
-- Indexes for table `feed_nutritions`
--
ALTER TABLE `feed_nutritions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farm_id` (`farm_id`);

--
-- Indexes for table `financial_transactions`
--
ALTER TABLE `financial_transactions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farm_id` (`farm_id`),
  ADD KEY `recorded_by` (`recorded_by`),
  ADD KEY `animal_id` (`animal_id`);

--
-- Indexes for table `goods_receipts`
--
ALTER TABLE `goods_receipts`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `grnNumber` (`grnNumber`),
  ADD KEY `purchaseOrderId` (`purchaseOrderId`),
  ADD KEY `vendorId` (`vendorId`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `receivedBy` (`receivedBy`);

--
-- Indexes for table `health_logs`
--
ALTER TABLE `health_logs`
  ADD PRIMARY KEY (`log_id`),
  ADD KEY `user_id` (`user_id`),
  ADD KEY `animal_id` (`animal_id`);

--
-- Indexes for table `inventory`
--
ALTER TABLE `inventory`
  ADD PRIMARY KEY (`id`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `productId` (`productId`);

--
-- Indexes for table `inventory_batches`
--
ALTER TABLE `inventory_batches`
  ADD PRIMARY KEY (`id`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `productId` (`productId`);

--
-- Indexes for table `inventory_history`
--
ALTER TABLE `inventory_history`
  ADD PRIMARY KEY (`id`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `productId` (`productId`);

--
-- Indexes for table `listings`
--
ALTER TABLE `listings`
  ADD PRIMARY KEY (`id`),
  ADD KEY `seller_id` (`seller_id`),
  ADD KEY `animal_id` (`animal_id`);

--
-- Indexes for table `notifications`
--
ALTER TABLE `notifications`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `offspring_records`
--
ALTER TABLE `offspring_records`
  ADD PRIMARY KEY (`id`),
  ADD KEY `birth_event_id` (`birth_event_id`),
  ADD KEY `offspring_id` (`offspring_id`),
  ADD KEY `farm_id` (`farm_id`);

--
-- Indexes for table `orders`
--
ALTER TABLE `orders`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `orderCode` (`orderCode`),
  ADD KEY `farmerId` (`farmerId`);

--
-- Indexes for table `orders_items`
--
ALTER TABLE `orders_items`
  ADD PRIMARY KEY (`id`),
  ADD KEY `productId` (`productId`),
  ADD KEY `farmerId` (`farmerId`),
  ADD KEY `orders_items_orderId_foreign_idx` (`orderId`);

--
-- Indexes for table `otpverifications`
--
ALTER TABLE `otpverifications`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`);

--
-- Indexes for table `productcategories`
--
ALTER TABLE `productcategories`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `production_performance`
--
ALTER TABLE `production_performance`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farm_id` (`farm_id`),
  ADD KEY `animal_id` (`animal_id`),
  ADD KEY `recorded_by` (`recorded_by`);

--
-- Indexes for table `products`
--
ALTER TABLE `products`
  ADD PRIMARY KEY (`id`),
  ADD KEY `productCategoryId` (`productCategoryId`),
  ADD KEY `productSubCategoryId` (`productSubCategoryId`),
  ADD KEY `products_addedByUserId_foreign_idx` (`addedByUserId`);

--
-- Indexes for table `productsubcategories`
--
ALTER TABLE `productsubcategories`
  ADD PRIMARY KEY (`id`),
  ADD KEY `categoryId` (`categoryId`);

--
-- Indexes for table `product_inventory`
--
ALTER TABLE `product_inventory`
  ADD PRIMARY KEY (`id`),
  ADD KEY `storeId` (`storeId`),
  ADD KEY `productId` (`productId`);

--
-- Indexes for table `purchase_orders`
--
ALTER TABLE `purchase_orders`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `poNumber` (`poNumber`),
  ADD KEY `purchase_orders_vendor_id` (`vendorId`),
  ADD KEY `purchase_orders_store_id` (`storeId`),
  ADD KEY `purchase_orders_status` (`status`),
  ADD KEY `purchase_orders_order_date` (`orderDate`);

--
-- Indexes for table `purchase_order_items`
--
ALTER TABLE `purchase_order_items`
  ADD PRIMARY KEY (`id`),
  ADD KEY `purchase_order_items_purchase_order_id` (`purchaseOrderId`),
  ADD KEY `purchase_order_items_product_id` (`productId`),
  ADD KEY `purchase_order_items_status` (`status`);

--
-- Indexes for table `questions`
--
ALTER TABLE `questions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `categoryId` (`categoryId`),
  ADD KEY `parentQuestionId` (`parentQuestionId`);

--
-- Indexes for table `sales_pipeline`
--
ALTER TABLE `sales_pipeline`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmId` (`farmId`);

--
-- Indexes for table `sales_pipeline_animals`
--
ALTER TABLE `sales_pipeline_animals`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_pipeline_animal` (`pipelineId`,`animalId`),
  ADD KEY `animalId` (`animalId`);

--
-- Indexes for table `sale_criteria_filters`
--
ALTER TABLE `sale_criteria_filters`
  ADD PRIMARY KEY (`id`),
  ADD KEY `farmId` (`farmId`);

--
-- Indexes for table `sequelizemeta`
--
ALTER TABLE `sequelizemeta`
  ADD PRIMARY KEY (`name`),
  ADD UNIQUE KEY `name` (`name`);

--
-- Indexes for table `stock_ledger`
--
ALTER TABLE `stock_ledger`
  ADD PRIMARY KEY (`id`),
  ADD KEY `createdByUserId` (`createdByUserId`),
  ADD KEY `stock_ledger_store_id` (`storeId`),
  ADD KEY `stock_ledger_product_id` (`productId`),
  ADD KEY `stock_ledger_batch_id` (`batchId`),
  ADD KEY `stock_ledger_transaction_type` (`transactionType`);

--
-- Indexes for table `stores`
--
ALTER TABLE `stores`
  ADD PRIMARY KEY (`id`),
  ADD KEY `storeTypeId` (`storeTypeId`);

--
-- Indexes for table `storetypes`
--
ALTER TABLE `storetypes`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `tokens`
--
ALTER TABLE `tokens`
  ADD PRIMARY KEY (`id`),
  ADD KEY `user` (`user`);

--
-- Indexes for table `userdetails`
--
ALTER TABLE `userdetails`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`),
  ADD KEY `storeId` (`storeId`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `vaccination_schedule`
--
ALTER TABLE `vaccination_schedule`
  ADD PRIMARY KEY (`id`),
  ADD KEY `addedByUserId` (`addedByUserId`);

--
-- Indexes for table `vendors`
--
ALTER TABLE `vendors`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `vendor_products`
--
ALTER TABLE `vendor_products`
  ADD PRIMARY KEY (`id`),
  ADD KEY `vendorId` (`vendorId`),
  ADD KEY `productId` (`productId`);

--
-- Indexes for table `whatsapp_chat`
--
ALTER TABLE `whatsapp_chat`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `messageId` (`messageId`),
  ADD KEY `userId` (`userId`);

--
-- Indexes for table `whatsapp_leads`
--
ALTER TABLE `whatsapp_leads`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `wa_id` (`wa_id`),
  ADD KEY `contacted_by` (`contacted_by`);

--
-- Indexes for table `whatsapp_lead_chat`
--
ALTER TABLE `whatsapp_lead_chat`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `messageId` (`messageId`),
  ADD KEY `userId` (`userId`);

--
-- Indexes for table `whatsapp_response`
--
ALTER TABLE `whatsapp_response`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `whatsapp_sessions`
--
ALTER TABLE `whatsapp_sessions`
  ADD PRIMARY KEY (`id`),
  ADD KEY `userId` (`userId`),
  ADD KEY `contacted_by` (`contacted_by`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `agent_location_history`
--
ALTER TABLE `agent_location_history`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `whatsapp_chat`
--
ALTER TABLE `whatsapp_chat`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `whatsapp_lead_chat`
--
ALTER TABLE `whatsapp_lead_chat`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `whatsapp_response`
--
ALTER TABLE `whatsapp_response`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `whatsapp_sessions`
--
ALTER TABLE `whatsapp_sessions`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `agents`
--
ALTER TABLE `agents`
  ADD CONSTRAINT `agents_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `agents_ibfk_2` FOREIGN KEY (`roleId`) REFERENCES `agentroles` (`id`),
  ADD CONSTRAINT `agents_ibfk_3` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`);

--
-- Constraints for table `agent_location_history`
--
ALTER TABLE `agent_location_history`
  ADD CONSTRAINT `agent_location_history_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`);

--
-- Constraints for table `animals`
--
ALTER TABLE `animals`
  ADD CONSTRAINT `animals_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`),
  ADD CONSTRAINT `animals_ibfk_2` FOREIGN KEY (`sire_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `animals_ibfk_3` FOREIGN KEY (`dam_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `animals_ibfk_4` FOREIGN KEY (`group_id`) REFERENCES `animal_groups` (`id`);

--
-- Constraints for table `animals_health_records`
--
ALTER TABLE `animals_health_records`
  ADD CONSTRAINT `animals_health_records_ibfk_1` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `animals_health_records_ibfk_2` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`),
  ADD CONSTRAINT `animals_health_records_ibfk_3` FOREIGN KEY (`administered_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `animal_groups`
--
ALTER TABLE `animal_groups`
  ADD CONSTRAINT `animal_groups_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`);

--
-- Constraints for table `animal_group_actions`
--
ALTER TABLE `animal_group_actions`
  ADD CONSTRAINT `animal_group_actions_ibfk_1` FOREIGN KEY (`groupId`) REFERENCES `animal_groups` (`id`);

--
-- Constraints for table `animal_group_rules`
--
ALTER TABLE `animal_group_rules`
  ADD CONSTRAINT `animal_group_rules_ibfk_1` FOREIGN KEY (`groupId`) REFERENCES `animal_groups` (`id`);

--
-- Constraints for table `animal_group_species`
--
ALTER TABLE `animal_group_species`
  ADD CONSTRAINT `animal_group_species_ibfk_1` FOREIGN KEY (`groupId`) REFERENCES `animal_groups` (`id`);

--
-- Constraints for table `animal_movements`
--
ALTER TABLE `animal_movements`
  ADD CONSTRAINT `animal_movements_ibfk_1` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`);

--
-- Constraints for table `answers`
--
ALTER TABLE `answers`
  ADD CONSTRAINT `answers_ibfk_1` FOREIGN KEY (`categoryId`) REFERENCES `categories` (`id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `answers_ibfk_2` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `answers_ibfk_3` FOREIGN KEY (`questionId`) REFERENCES `questions` (`id`) ON UPDATE CASCADE;

--
-- Constraints for table `appointments`
--
ALTER TABLE `appointments`
  ADD CONSTRAINT `appointments_healthLogId_foreign_idx` FOREIGN KEY (`healthLogId`) REFERENCES `health_logs` (`log_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `appointments_ibfk_1` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`),
  ADD CONSTRAINT `appointments_ibfk_2` FOREIGN KEY (`addedByUserId`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `appointments_ibfk_3` FOREIGN KEY (`doctorId`) REFERENCES `users` (`id`);

--
-- Constraints for table `birth_events`
--
ALTER TABLE `birth_events`
  ADD CONSTRAINT `birth_events_ibfk_1` FOREIGN KEY (`breeding_event_id`) REFERENCES `breeding_events` (`id`),
  ADD CONSTRAINT `birth_events_ibfk_2` FOREIGN KEY (`dam_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `birth_events_ibfk_3` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`);

--
-- Constraints for table `breeding_events`
--
ALTER TABLE `breeding_events`
  ADD CONSTRAINT `breeding_events_ibfk_1` FOREIGN KEY (`dam_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `breeding_events_ibfk_2` FOREIGN KEY (`sire_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `breeding_events_ibfk_3` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`);

--
-- Constraints for table `farmers`
--
ALTER TABLE `farmers`
  ADD CONSTRAINT `farmers_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `farmers_ibfk_3` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `farmers_onboardedBy_foreign_idx` FOREIGN KEY (`onboardedBy`) REFERENCES `users` (`id`);

--
-- Constraints for table `farms`
--
ALTER TABLE `farms`
  ADD CONSTRAINT `farms_ibfk_1` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`);

--
-- Constraints for table `farm_diseases`
--
ALTER TABLE `farm_diseases`
  ADD CONSTRAINT `farm_diseases_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`);

--
-- Constraints for table `farm_images`
--
ALTER TABLE `farm_images`
  ADD CONSTRAINT `farm_images_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`);

--
-- Constraints for table `feed_nutritions`
--
ALTER TABLE `feed_nutritions`
  ADD CONSTRAINT `feed_nutritions_ibfk_1` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`);

--
-- Constraints for table `financial_transactions`
--
ALTER TABLE `financial_transactions`
  ADD CONSTRAINT `financial_transactions_ibfk_1` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`),
  ADD CONSTRAINT `financial_transactions_ibfk_2` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `financial_transactions_ibfk_3` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`);

--
-- Constraints for table `goods_receipts`
--
ALTER TABLE `goods_receipts`
  ADD CONSTRAINT `goods_receipts_ibfk_1` FOREIGN KEY (`purchaseOrderId`) REFERENCES `purchase_orders` (`id`),
  ADD CONSTRAINT `goods_receipts_ibfk_2` FOREIGN KEY (`vendorId`) REFERENCES `vendors` (`id`),
  ADD CONSTRAINT `goods_receipts_ibfk_3` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `goods_receipts_ibfk_4` FOREIGN KEY (`receivedBy`) REFERENCES `users` (`id`);

--
-- Constraints for table `health_logs`
--
ALTER TABLE `health_logs`
  ADD CONSTRAINT `health_logs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT `health_logs_ibfk_2` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;

--
-- Constraints for table `inventory`
--
ALTER TABLE `inventory`
  ADD CONSTRAINT `inventory_ibfk_1` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `inventory_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `inventory_batches`
--
ALTER TABLE `inventory_batches`
  ADD CONSTRAINT `inventory_batches_ibfk_1` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `inventory_batches_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `inventory_history`
--
ALTER TABLE `inventory_history`
  ADD CONSTRAINT `inventory_history_ibfk_1` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `inventory_history_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `listings`
--
ALTER TABLE `listings`
  ADD CONSTRAINT `listings_ibfk_1` FOREIGN KEY (`seller_id`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `listings_ibfk_2` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`);

--
-- Constraints for table `offspring_records`
--
ALTER TABLE `offspring_records`
  ADD CONSTRAINT `offspring_records_ibfk_1` FOREIGN KEY (`birth_event_id`) REFERENCES `birth_events` (`id`),
  ADD CONSTRAINT `offspring_records_ibfk_2` FOREIGN KEY (`offspring_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `offspring_records_ibfk_3` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`);

--
-- Constraints for table `orders`
--
ALTER TABLE `orders`
  ADD CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`);

--
-- Constraints for table `orders_items`
--
ALTER TABLE `orders_items`
  ADD CONSTRAINT `orders_items_ibfk_1` FOREIGN KEY (`productId`) REFERENCES `products` (`id`),
  ADD CONSTRAINT `orders_items_ibfk_2` FOREIGN KEY (`farmerId`) REFERENCES `farmers` (`id`),
  ADD CONSTRAINT `orders_items_orderId_foreign_idx` FOREIGN KEY (`orderId`) REFERENCES `orders` (`id`);

--
-- Constraints for table `otpverifications`
--
ALTER TABLE `otpverifications`
  ADD CONSTRAINT `otpverifications_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`) ON UPDATE CASCADE;

--
-- Constraints for table `production_performance`
--
ALTER TABLE `production_performance`
  ADD CONSTRAINT `production_performance_ibfk_1` FOREIGN KEY (`farm_id`) REFERENCES `farms` (`id`),
  ADD CONSTRAINT `production_performance_ibfk_2` FOREIGN KEY (`animal_id`) REFERENCES `animals` (`id`),
  ADD CONSTRAINT `production_performance_ibfk_3` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`);

--
-- Constraints for table `products`
--
ALTER TABLE `products`
  ADD CONSTRAINT `products_addedByUserId_foreign_idx` FOREIGN KEY (`addedByUserId`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `products_ibfk_1` FOREIGN KEY (`productCategoryId`) REFERENCES `productcategories` (`id`),
  ADD CONSTRAINT `products_ibfk_2` FOREIGN KEY (`productSubCategoryId`) REFERENCES `productsubcategories` (`id`);

--
-- Constraints for table `productsubcategories`
--
ALTER TABLE `productsubcategories`
  ADD CONSTRAINT `productsubcategories_ibfk_1` FOREIGN KEY (`categoryId`) REFERENCES `productcategories` (`id`);

--
-- Constraints for table `product_inventory`
--
ALTER TABLE `product_inventory`
  ADD CONSTRAINT `product_inventory_ibfk_1` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `product_inventory_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `purchase_orders`
--
ALTER TABLE `purchase_orders`
  ADD CONSTRAINT `purchase_orders_ibfk_1` FOREIGN KEY (`vendorId`) REFERENCES `vendors` (`id`),
  ADD CONSTRAINT `purchase_orders_ibfk_2` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`);

--
-- Constraints for table `purchase_order_items`
--
ALTER TABLE `purchase_order_items`
  ADD CONSTRAINT `purchase_order_items_ibfk_1` FOREIGN KEY (`purchaseOrderId`) REFERENCES `purchase_orders` (`id`),
  ADD CONSTRAINT `purchase_order_items_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `questions`
--
ALTER TABLE `questions`
  ADD CONSTRAINT `questions_ibfk_1` FOREIGN KEY (`categoryId`) REFERENCES `categories` (`id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `questions_ibfk_2` FOREIGN KEY (`parentQuestionId`) REFERENCES `questions` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;

--
-- Constraints for table `sales_pipeline`
--
ALTER TABLE `sales_pipeline`
  ADD CONSTRAINT `sales_pipeline_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`);

--
-- Constraints for table `sales_pipeline_animals`
--
ALTER TABLE `sales_pipeline_animals`
  ADD CONSTRAINT `sales_pipeline_animals_ibfk_1` FOREIGN KEY (`pipelineId`) REFERENCES `sales_pipeline` (`id`),
  ADD CONSTRAINT `sales_pipeline_animals_ibfk_2` FOREIGN KEY (`animalId`) REFERENCES `animals` (`id`);

--
-- Constraints for table `sale_criteria_filters`
--
ALTER TABLE `sale_criteria_filters`
  ADD CONSTRAINT `sale_criteria_filters_ibfk_1` FOREIGN KEY (`farmId`) REFERENCES `farms` (`id`);

--
-- Constraints for table `stock_ledger`
--
ALTER TABLE `stock_ledger`
  ADD CONSTRAINT `stock_ledger_ibfk_1` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`),
  ADD CONSTRAINT `stock_ledger_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`),
  ADD CONSTRAINT `stock_ledger_ibfk_3` FOREIGN KEY (`batchId`) REFERENCES `inventory_batches` (`id`),
  ADD CONSTRAINT `stock_ledger_ibfk_4` FOREIGN KEY (`createdByUserId`) REFERENCES `users` (`id`);

--
-- Constraints for table `stores`
--
ALTER TABLE `stores`
  ADD CONSTRAINT `stores_ibfk_1` FOREIGN KEY (`storeTypeId`) REFERENCES `storetypes` (`id`);

--
-- Constraints for table `tokens`
--
ALTER TABLE `tokens`
  ADD CONSTRAINT `tokens_ibfk_1` FOREIGN KEY (`user`) REFERENCES `users` (`id`);

--
-- Constraints for table `userdetails`
--
ALTER TABLE `userdetails`
  ADD CONSTRAINT `userdetails_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`),
  ADD CONSTRAINT `userdetails_ibfk_2` FOREIGN KEY (`storeId`) REFERENCES `stores` (`id`);

--
-- Constraints for table `vaccination_schedule`
--
ALTER TABLE `vaccination_schedule`
  ADD CONSTRAINT `vaccination_schedule_ibfk_1` FOREIGN KEY (`addedByUserId`) REFERENCES `users` (`id`);

--
-- Constraints for table `vendor_products`
--
ALTER TABLE `vendor_products`
  ADD CONSTRAINT `vendor_products_ibfk_1` FOREIGN KEY (`vendorId`) REFERENCES `vendors` (`id`),
  ADD CONSTRAINT `vendor_products_ibfk_2` FOREIGN KEY (`productId`) REFERENCES `products` (`id`);

--
-- Constraints for table `whatsapp_chat`
--
ALTER TABLE `whatsapp_chat`
  ADD CONSTRAINT `whatsapp_chat_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`) ON UPDATE CASCADE;

--
-- Constraints for table `whatsapp_leads`
--
ALTER TABLE `whatsapp_leads`
  ADD CONSTRAINT `whatsapp_leads_ibfk_1` FOREIGN KEY (`contacted_by`) REFERENCES `users` (`id`) ON UPDATE CASCADE;

--
-- Constraints for table `whatsapp_lead_chat`
--
ALTER TABLE `whatsapp_lead_chat`
  ADD CONSTRAINT `whatsapp_lead_chat_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `whatsapp_leads` (`id`) ON UPDATE CASCADE;

--
-- Constraints for table `whatsapp_sessions`
--
ALTER TABLE `whatsapp_sessions`
  ADD CONSTRAINT `whatsapp_sessions_ibfk_1` FOREIGN KEY (`userId`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  ADD CONSTRAINT `whatsapp_sessions_ibfk_2` FOREIGN KEY (`contacted_by`) REFERENCES `users` (`id`) ON DELETE SET NULL ON UPDATE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
