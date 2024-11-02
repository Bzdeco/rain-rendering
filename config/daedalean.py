# Daedalean database configuration file
import os
from pathlib import Path

from config.utils import focal_length_mm, intrinsics, compute_camera_motion_velocities


DATASET_FOLDER = Path("/home/bzdeco/Documents/EPFL/CVLab/Final/adverse-weather-eval/rain_datasets/data/source/daedalean")
RAIN_FALLRATE = 10  # in mm/h  FIXME: adjust accordingly to severity


def resolve_paths(params):
    # List sequences path (relative to dataset folder)
    # Let's just consider any subfolder is a sequence
    params.sequences = [x for x in os.listdir(params.images_root) if os.path.isdir(os.path.join(params.images_root, x))]
    assert (len(params.sequences) > 0), "There are no valid sequences folder in the dataset root"

    # Set source image directory
    params.images = {s: os.path.join(params.dataset_root, s, "rgb") for s in params.sequences}

    # Set calibration (Kitti format) directory IF ANY (optional)
    params.calib = {s: None for s in params.sequences}

    # Set depth directory
    params.depth = {s: os.path.join(params.dataset_root, s, "depth") for s in params.sequences}

    return params

def settings():
    settings = {}

    # Camera intrinsic parameters
    settings["cam_hz"] = 6                       # Camera Hz (aka FPS) – I guess it's irrelevant as we only have some frames
    settings["cam_CCD_WH"] = [4096, 3000]        # Camera CDD Width and Height (pixels)
    settings["cam_CCD_pixsize"] = 4.65           # Camera CDD pixel size (micro meters) FIXME
    settings["cam_WH"] = [4096, 3000]            # Camera image Width and Height (pixels)
    settings["cam_focal"] = 6                    # Focal length (mm) – set for each recording from intrinsics
    settings["cam_gain"] = 20                    # Camera gain FIXME
    settings["cam_f_number"] = 6.0               # F-Number FIXME
    settings["cam_focus_plane"] = 100_000_000.0  # Focus plane (meter) – approximate "infinity", i.e. far away
    settings["cam_exposure"] = 2                 # Camera exposure (ms) FIXME

    # Camera extrinsic parameters (right-handed coordinate system)  FIXME should those be changed for a more appropriate angle?
    settings["cam_pos"] = [1.5, 1.5, 0.3]     # Camera pos (meter)
    settings["cam_lookat"] = [1.5, 1.5, -1.]  # Camera look at vector (meter)
    settings["cam_up"] = [0., 1., 0.]         # Camera up vector (meter)

    # Sequence-wise settings
    # Note: sequence object and settings are merged, hence any setting can be overwritten sequence-wise
    settings["sequences"] = {}

    for sequence_folder in DATASET_FOLDER.glob("*"):
        sequence = sequence_folder.name
        separator_idx = sequence.rfind("/")
        recording = f"{sequence[:separator_idx]}/{sequence[separator_idx + 1:]}"
        frames_filepaths = list((sequence_folder / "rgb").glob("*.png"))
        timestamps = list(map(lambda fp: int(fp.stem), frames_filepaths))
        n_frames = len(frames_filepaths)

        settings["sequences"][sequence] = {}
        settings["sequences"][sequence]["cam_focal"] = focal_length_mm(
            intrinsics_matrix=intrinsics(recording),
            sensor_width_mm=settings["cam_CCD_pixsize"] * settings["cam_CCD_WH"][0] * 1e-3,
            image_width_px=settings["cam_CCD_WH"][0]
        )
        settings["sequences"][sequence]["sim_mode"] = "steps"
        settings["sequences"][sequence]["sim_steps"] = {
            "cam_motion": compute_camera_motion_velocities(recording, timestamps),  # in km/h
            "rain_fallrate": [RAIN_FALLRATE] * n_frames
        }

    return settings
