# <div align="center"><b> PETWB-REP </b></div>
[**📕zenodo**](https://zenodo.org/records/16789748)

This is the official repository for **PETWB-REP: A Dataset of Whole-body PET/CT Scans with Paired Radiology Reports**, in which we provide scripts for whole-body image processing.
Preprocessing steps include:
* **Anonymization**: Removing patient identifiers from metadata.
* **Facial stripping**: Removing facial features to ensure privacy.
* **SUV calculation**: Computing Standardized Uptake Value (SUV) for PET images and align CT images to PET space.
## To get started
```bash
git clone https://github.com/R1pples/PETWB-REP.git
```
## Anonymization
Patient identifiers and sensitive metadata were removed using the [RSNA DICOM Anonymizer (V18.0)](https://github.com/RSNA/Anonymizer) to remove the identifiers. The process follows standard de-identification protocols to ensure data privacy and compliance with ethical guidelines.
## Facial stripping
Facial features were removed using an adapted version of [CTA-DEFACE](https://github.com/CCI-Bonn/CTA-DEFACE), specifically optimized for our whole-body PET/CT dataset to ensure robust de-identification.
```bash
git clone https://github.com/CCI-Bonn/CTA-DEFACE.git
cp -r ./run_deface_WB.py ./CTA-DEFACE
cd ./CTA-DEFACE
python run_deface_WB.py -i ./input -o ./output
```

## SUV calculation
To calculate SUV and align CT images to PET space, run the following command:

```bash
python suv_calculate.py \
    --bids_root ./data/bids \
    --dicom_root ./data/raw_dicom \
    --db ./private/anonymizer.db \
    --output ./processed_data
