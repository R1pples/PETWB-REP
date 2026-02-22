import os
import glob
import sqlite3
import datetime
import argparse
import logging
import pydicom
import SimpleITK as sitk
import numpy as np

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def parse_time(tm_str):
    if not tm_str:
        return None
    try:
        if '.' in tm_str:
            return datetime.datetime.strptime(tm_str, "%H%M%S.%f")
        return datetime.datetime.strptime(tm_str, "%H%M%S")
    except ValueError:
        return None

def get_original_id(db_path, anon_id):
    """Query the mapping database for the original patient ID."""
    if not os.path.exists(db_path):
        logging.error(f"Database not found at {db_path}")
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT patient_id FROM phi WHERE anon_patient_id=?", (anon_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        logging.error(f"Database query error: {e}")
        return None

def extract_suv_parameters(dicom_folder):
    """Search for PET metadata in original DICOM files."""
    if not os.path.exists(dicom_folder):
        return None
    
    for root, _, files in os.walk(dicom_folder):
        for f in files:
            if not (f.lower().endswith('.dcm') or '.' not in f):
                continue
            try:
                ds = pydicom.dcmread(os.path.join(root, f), stop_before_pixels=True)
                if ds.get('Modality') != 'PT':
                    continue
                
                if hasattr(ds, 'PatientWeight') and hasattr(ds, 'RadiopharmaceuticalInformationSequence'):
                    seq = ds.RadiopharmaceuticalInformationSequence[0]
                    return {
                        'weight': float(ds.PatientWeight),
                        'dose': float(seq.RadionuclideTotalDose),
                        'halflife': float(seq.RadionuclideHalfLife),
                        'start_time': seq.RadiopharmaceuticalStartTime,
                        'scan_time': ds.SeriesTime
                    }
            except Exception:
                continue
    return None

def calculate_suv_factor(info):
    """Calculate the SUV conversion factor based on decay-corrected dose."""
    if not info:
        return None
    try:
        t0 = parse_time(info['start_time'])
        t1 = parse_time(info['scan_time'])
        decay_factor = 1.0
        
        if t0 and t1:
            if t1 < t0: 
                t1 += datetime.timedelta(days=1)
            dt = (t1 - t0).total_seconds()
            decay_factor = 2 ** (-dt / info['halflife'])
        
        final_dose = info['dose'] * decay_factor
        if final_dose == 0:
            return None
        return (info['weight'] * 1000) / final_dose
    except Exception:
        return None

def find_bids_file(subject_path, modality, suffix):
    """Locate NIfTI files in BIDS directory structure (supports sessions)."""
    # Try direct: sub-xx/modality/*.nii.gz
    # Try session: sub-xx/ses-*/modality/*.nii.gz
    patterns = [
        os.path.join(subject_path, modality, f"*{suffix}*.nii.gz"),
        os.path.join(subject_path, "ses-*", modality, f"*{suffix}*.nii.gz")
    ]
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    return None

def process_subject(sub_path, args):
    sub_name = os.path.basename(sub_path)
    anon_id = sub_name.replace('sub-', '')
    
    # 1. Map ID
    original_id = get_original_id(args.db, anon_id)
    if not original_id:
        logging.warning(f"Skipping {sub_name}: ID not found in database.")
        return

    # 2. Check Original DICOMs
    dicom_dir = os.path.join(args.dicom_root, original_id)
    params = extract_suv_parameters(dicom_dir)
    suv_factor = calculate_suv_factor(params)
    
    if suv_factor is None:
        logging.warning(f"Skipping {sub_name}: Failed to extract SUV parameters from {dicom_dir}")
        return

    # 3. Locate NIfTIs
    ct_file = find_bids_file(sub_path, 'anat', 'ct')
    pet_file = find_bids_file(sub_path, 'pet', 'pet')
    
    if not ct_file or not pet_file:
        logging.warning(f"Skipping {sub_name}: Missing CT or PET NIfTI files.")
        return

    # 4. Processing
    logging.info(f"Processing {sub_name} | SUV Factor: {suv_factor:.4f}")
    try:
        pet_img = sitk.ReadImage(pet_file)
        ct_img = sitk.ReadImage(ct_file)
        
        # Convert to SUV
        pet_suv = sitk.Cast(pet_img, sitk.sitkFloat32) * suv_factor
        
        # Resample CT to PET space (Registration)
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(pet_suv)
        resampler.SetInterpolator(sitk.sitkLinear)
        resampler.SetDefaultPixelValue(-1000)
        resampler.SetOutputPixelType(sitk.sitkFloat32)
        resampler.SetTransform(sitk.Transform())
        ct_res = resampler.Execute(ct_img)
        
        # Save output
        out_dir = os.path.join(args.output, anon_id)
        os.makedirs(out_dir, exist_ok=True)
        sitk.WriteImage(pet_suv, os.path.join(out_dir, f"{anon_id}_pet_suv.nii.gz"))
        sitk.WriteImage(ct_res, os.path.join(out_dir, f"{anon_id}_ct_res.nii.gz"))
        logging.info(f"Successfully saved to {out_dir}")
        
    except Exception as e:
        logging.error(f"Error processing {sub_name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Calculate SUV and Resample CT to PET space.")
    parser.add_argument("--bids_root", required=True, help="Path to BIDS formatted NIfTI data")
    parser.add_argument("--dicom_root", required=True, help="Path to original raw DICOM folders")
    parser.add_argument("--db", required=True, help="Path to the anonymization SQLite database")
    parser.add_argument("--output", required=True, help="Path to save processed results")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    subjects = glob.glob(os.path.join(args.bids_root, 'sub-*'))
    logging.info(f"Found {len(subjects)} subjects. Starting batch processing...")
    
    for sub in subjects:
        process_subject(sub, args)

if __name__ == "__main__":
    main()