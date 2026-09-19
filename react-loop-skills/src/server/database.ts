import sqlite3 from 'sqlite3';
import { open, Database } from 'sqlite';
import path from 'path';

export class LocalDatabase {
  private db: Database | null = null;
  private dbPath: string;

  constructor(dbPath: string = './data/local.db') {
    this.dbPath = dbPath;
  }

  async initialize(): Promise<void> {
    this.db = await open({
      filename: this.dbPath,
      driver: sqlite3.Database,
    });

    console.log(`[Database] Connected to ${this.dbPath}`);
    await this.createTables();
  }

  private async createTables(): Promise<void> {
    // Farmers table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS farmers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        email TEXT,
        address TEXT,
        village TEXT,
        district TEXT,
        state TEXT,
        registration_date TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    // Farms table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS farms (
        id TEXT PRIMARY KEY,
        farmer_id TEXT NOT NULL,
        name TEXT NOT NULL,
        total_area REAL,
        area_unit TEXT DEFAULT 'acres',
        soil_type TEXT,
        irrigation_type TEXT,
        address TEXT,
        coordinates TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmers(id)
      )
    `);

    // Fields table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS fields (
        id TEXT PRIMARY KEY,
        farm_id TEXT NOT NULL,
        name TEXT NOT NULL,
        area REAL,
        current_crop TEXT,
        soil_quality TEXT,
        FOREIGN KEY (farm_id) REFERENCES farms(id)
      )
    `);

    // Animals table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS animals (
        id TEXT PRIMARY KEY,
        farmer_id TEXT NOT NULL,
        tag_number TEXT NOT NULL,
        name TEXT,
        type TEXT NOT NULL,
        breed TEXT,
        date_of_birth TEXT,
        gender TEXT,
        color TEXT,
        weight REAL,
        health_status TEXT DEFAULT 'healthy',
        acquisition_date TEXT,
        purchase_price REAL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmers(id)
      )
    `);

    // Crops table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS crops (
        id TEXT PRIMARY KEY,
        farmer_id TEXT NOT NULL,
        name TEXT NOT NULL,
        variety TEXT,
        field_id TEXT,
        area_acres REAL,
        planting_date TEXT,
        expected_harvest TEXT,
        status TEXT DEFAULT 'planted',
        season TEXT,
        yield_expected REAL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmers(id),
        FOREIGN KEY (field_id) REFERENCES fields(id)
      )
    `);

    // Health records table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS health_records (
        id TEXT PRIMARY KEY,
        animal_id TEXT NOT NULL,
        farmer_id TEXT NOT NULL,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        symptoms TEXT,
        diagnosis TEXT,
        treatment TEXT,
        vet_name TEXT,
        follow_up_required BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (animal_id) REFERENCES animals(id),
        FOREIGN KEY (farmer_id) REFERENCES farmers(id)
      )
    `);

    // Production table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS production (
        id TEXT PRIMARY KEY,
        animal_id TEXT NOT NULL,
        date TEXT NOT NULL,
        quantity REAL NOT NULL,
        unit TEXT DEFAULT 'liters',
        quality TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (animal_id) REFERENCES animals(id)
      )
    `);

    // Vaccinations table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS vaccinations (
        id TEXT PRIMARY KEY,
        animal_id TEXT NOT NULL,
        farmer_id TEXT NOT NULL,
        vaccine_name TEXT NOT NULL,
        scheduled_date TEXT NOT NULL,
        completed_date TEXT,
        status TEXT DEFAULT 'scheduled',
        next_due TEXT,
        vet_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (animal_id) REFERENCES animals(id),
        FOREIGN KEY (farmer_id) REFERENCES farmers(id)
      )
    `);

    // Appointments table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        farmer_id TEXT NOT NULL,
        type TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        reason TEXT,
        animal_id TEXT,
        vet_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmers(id),
        FOREIGN KEY (animal_id) REFERENCES animals(id)
      )
    `);

    // Sessions table for chat
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        farmer_id TEXT NOT NULL,
        context TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (farmer_id) REFERENCES farmers(id)
      )
    `);

    // Messages table
    await this.db?.exec(`
      CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        skill_id TEXT,
        tool_calls TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
      )
    `);

    console.log('[Database] All tables created successfully');
  }

  async seedData(): Promise<void> {
    // Seed farmers
    const farmers = [
      ['farmer_001', 'Rajesh Kumar', '9876543210', 'rajesh@example.com', 'Village Khera', 'Khera', 'Muzaffarnagar', 'Uttar Pradesh', '2023-01-15'],
      ['farmer_002', 'Amit Singh', '9876543211', 'amit@example.com', 'Village Rampur', 'Rampur', 'Meerut', 'Uttar Pradesh', '2023-03-20'],
      ['farmer_003', 'Priya Patel', '9876543212', 'priya@example.com', 'Village Anand', 'Anand', 'Ahmedabad', 'Gujarat', '2023-05-10'],
    ];

    for (const farmer of farmers) {
      await this.db?.run(
        `INSERT OR IGNORE INTO farmers (id, name, phone, email, address, village, district, state, registration_date) 
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        farmer
      );
    }

    // Seed farms
    await this.db?.run(
      `INSERT OR IGNORE INTO farms (id, farmer_id, name, total_area, area_unit, soil_type, irrigation_type, address, coordinates) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['farm_001', 'farmer_001', 'Khera Farm', 12.5, 'acres', 'loamy', 'canal', 'Village Khera, Muzaffarnagar', '29.4500,77.7000']
    );

    // Seed fields
    const fields = [
      ['field_001', 'farm_001', 'Field A', 4.5, 'wheat', 'good'],
      ['field_002', 'farm_001', 'Field B', 5.0, 'rice', 'excellent'],
      ['field_003', 'farm_001', 'Field C', 3.0, null, 'good'],
    ];
    for (const field of fields) {
      await this.db?.run(
        `INSERT OR IGNORE INTO fields (id, farm_id, name, area, current_crop, soil_quality) VALUES (?, ?, ?, ?, ?, ?)`,
        field
      );
    }

    // Seed animals
    const animals = [
      ['animal_001', 'farmer_001', 'COW001', 'Gauri', 'cow', 'Sahiwal', '2020-05-15', 'female', 'brown', 450, 'healthy', '2021-06-20', 45000],
      ['animal_002', 'farmer_001', 'BUF001', 'Lakshmi', 'buffalo', 'Murrah', '2019-08-10', 'female', 'black', 550, 'healthy', '2020-09-15', 65000],
      ['animal_003', 'farmer_001', 'GOAT001', 'Moti', 'goat', 'Jamunapari', '2022-02-20', 'male', 'white', 45, 'healthy', '2022-05-10', 8000],
      ['animal_004', 'farmer_001', 'COW002', 'Parvati', 'cow', 'Gir', '2021-03-10', 'female', 'white', 420, 'healthy', '2022-04-15', 52000],
      ['animal_005', 'farmer_002', 'BUF002', 'Durga', 'buffalo', 'Mehsana', '2020-11-05', 'female', 'grey', 480, 'healthy', '2021-12-20', 58000],
    ];
    for (const animal of animals) {
      await this.db?.run(
        `INSERT OR IGNORE INTO animals (id, farmer_id, tag_number, name, type, breed, date_of_birth, gender, color, weight, health_status, acquisition_date, purchase_price) 
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        animal
      );
    }

    // Seed crops
    const crops = [
      ['crop_001', 'farmer_001', 'Wheat', 'HD-2967', 'field_001', 4.5, '2025-11-15', '2026-04-20', 'growing', 'rabi', 18],
      ['crop_002', 'farmer_001', 'Rice', 'Pusa Basmati', 'field_002', 5.0, '2026-06-20', '2026-10-30', 'planted', 'kharif', 22],
    ];
    for (const crop of crops) {
      await this.db?.run(
        `INSERT OR IGNORE INTO crops (id, farmer_id, name, variety, field_id, area_acres, planting_date, expected_harvest, status, season, yield_expected) 
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        crop
      );
    }

    // Seed health records
    await this.db?.run(
      `INSERT OR IGNORE INTO health_records (id, animal_id, farmer_id, date, type, symptoms, diagnosis, treatment, vet_name, follow_up_required) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['health_001', 'animal_001', 'farmer_001', '2026-09-10', 'checkup', 'none', 'healthy', 'routine check', 'Dr. Sharma', 0]
    );

    await this.db?.run(
      `INSERT OR IGNORE INTO health_records (id, animal_id, farmer_id, date, type, symptoms, diagnosis, treatment, vet_name, follow_up_required) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['health_002', 'animal_002', 'farmer_001', '2026-09-05', 'treatment', 'fever, reduced appetite', 'mild infection', 'antibiotics for 5 days', 'Dr. Verma', 1]
    );

    // Seed production
    const production = [
      ['prod_001', 'animal_001', '2026-09-19', 12.5, 'liters', 'A'],
      ['prod_002', 'animal_001', '2026-09-18', 13.0, 'liters', 'A'],
      ['prod_003', 'animal_001', '2026-09-17', 12.8, 'liters', 'A'],
      ['prod_004', 'animal_002', '2026-09-19', 8.5, 'liters', 'A'],
      ['prod_005', 'animal_002', '2026-09-18', 9.0, 'liters', 'A'],
    ];
    for (const prod of production) {
      await this.db?.run(
        `INSERT OR IGNORE INTO production (id, animal_id, date, quantity, unit, quality) VALUES (?, ?, ?, ?, ?, ?)`,
        prod
      );
    }

    // Seed vaccinations
    await this.db?.run(
      `INSERT OR IGNORE INTO vaccinations (id, animal_id, farmer_id, vaccine_name, scheduled_date, completed_date, status, next_due, vet_name) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['vac_001', 'animal_001', 'farmer_001', 'FMD Vaccine', '2026-10-15', null, 'scheduled', '2027-10-15', 'Dr. Sharma']
    );

    await this.db?.run(
      `INSERT OR IGNORE INTO vaccinations (id, animal_id, farmer_id, vaccine_name, scheduled_date, completed_date, status, next_due, vet_name) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['vac_002', 'animal_002', 'farmer_001', 'FMD Vaccine', '2026-10-15', '2026-09-01', 'completed', '2027-10-15', 'Dr. Sharma']
    );

    // Seed appointments
    await this.db?.run(
      `INSERT OR IGNORE INTO appointments (id, farmer_id, type, date, time, status, reason, animal_id, vet_name) 
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ['apt_001', 'farmer_001', 'veterinary', '2026-09-20', '10:00', 'confirmed', 'Vaccination', 'animal_001', 'Dr. Sharma']
    );

    console.log('[Database] Seed data inserted successfully');
  }

  getDb(): Database | null {
    return this.db;
  }

  async close(): Promise<void> {
    if (this.db) {
      await this.db.close();
      console.log('[Database] Connection closed');
    }
  }
}

// Singleton
let globalDb: LocalDatabase | null = null;

export function createDatabase(dbPath?: string): LocalDatabase {
  globalDb = new LocalDatabase(dbPath);
  return globalDb;
}

export function getDatabase(): LocalDatabase {
  if (!globalDb) {
    throw new Error('Database not initialized. Call createDatabase first.');
  }
  return globalDb;
}
