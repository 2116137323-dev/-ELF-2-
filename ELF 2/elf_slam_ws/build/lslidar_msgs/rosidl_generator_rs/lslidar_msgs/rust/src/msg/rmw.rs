#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};


#[link(name = "lslidar_msgs__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarDifop() -> *const std::ffi::c_void;
}

#[link(name = "lslidar_msgs__rosidl_generator_c")]
extern "C" {
    fn lslidar_msgs__msg__LslidarDifop__init(msg: *mut LslidarDifop) -> bool;
    fn lslidar_msgs__msg__LslidarDifop__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<LslidarDifop>, size: usize) -> bool;
    fn lslidar_msgs__msg__LslidarDifop__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<LslidarDifop>);
    fn lslidar_msgs__msg__LslidarDifop__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<LslidarDifop>, out_seq: *mut rosidl_runtime_rs::Sequence<LslidarDifop>) -> bool;
}

// Corresponds to lslidar_msgs__msg__LslidarDifop
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]


// This struct is not documented.
#[allow(missing_docs)]

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarDifop {

    // This member is not documented.
    #[allow(missing_docs)]
    pub temperature: i64,


    // This member is not documented.
    #[allow(missing_docs)]
    pub rpm: i64,

}



impl Default for LslidarDifop {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !lslidar_msgs__msg__LslidarDifop__init(&mut msg as *mut _) {
        panic!("Call to lslidar_msgs__msg__LslidarDifop__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for LslidarDifop {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarDifop__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarDifop__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarDifop__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for LslidarDifop {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for LslidarDifop where Self: Sized {
  const TYPE_NAME: &'static str = "lslidar_msgs/msg/LslidarDifop";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarDifop() }
  }
}


#[link(name = "lslidar_msgs__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarPacket() -> *const std::ffi::c_void;
}

#[link(name = "lslidar_msgs__rosidl_generator_c")]
extern "C" {
    fn lslidar_msgs__msg__LslidarPacket__init(msg: *mut LslidarPacket) -> bool;
    fn lslidar_msgs__msg__LslidarPacket__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<LslidarPacket>, size: usize) -> bool;
    fn lslidar_msgs__msg__LslidarPacket__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<LslidarPacket>);
    fn lslidar_msgs__msg__LslidarPacket__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<LslidarPacket>, out_seq: *mut rosidl_runtime_rs::Sequence<LslidarPacket>) -> bool;
}

// Corresponds to lslidar_msgs__msg__LslidarPacket
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]

/// Raw Leishen LIDAR packet.

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarPacket {
    /// packet timestamp
    pub stamp: builtin_interfaces::msg::rmw::Time,

    /// packet contents
    #[cfg_attr(feature = "serde", serde(with = "serde_big_array::BigArray"))]
    pub data: [u8; 2000],

}



impl Default for LslidarPacket {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !lslidar_msgs__msg__LslidarPacket__init(&mut msg as *mut _) {
        panic!("Call to lslidar_msgs__msg__LslidarPacket__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for LslidarPacket {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPacket__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPacket__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPacket__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for LslidarPacket {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for LslidarPacket where Self: Sized {
  const TYPE_NAME: &'static str = "lslidar_msgs/msg/LslidarPacket";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarPacket() }
  }
}


#[link(name = "lslidar_msgs__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarPoint() -> *const std::ffi::c_void;
}

#[link(name = "lslidar_msgs__rosidl_generator_c")]
extern "C" {
    fn lslidar_msgs__msg__LslidarPoint__init(msg: *mut LslidarPoint) -> bool;
    fn lslidar_msgs__msg__LslidarPoint__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<LslidarPoint>, size: usize) -> bool;
    fn lslidar_msgs__msg__LslidarPoint__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<LslidarPoint>);
    fn lslidar_msgs__msg__LslidarPoint__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<LslidarPoint>, out_seq: *mut rosidl_runtime_rs::Sequence<LslidarPoint>) -> bool;
}

// Corresponds to lslidar_msgs__msg__LslidarPoint
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]

/// Time when the point is captured

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarPoint {

    // This member is not documented.
    #[allow(missing_docs)]
    pub time: f32,

    /// Converted distance in the sensor frame
    pub x: f64,


    // This member is not documented.
    #[allow(missing_docs)]
    pub y: f64,


    // This member is not documented.
    #[allow(missing_docs)]
    pub z: f64,

    /// Raw measurement from Leishen M10
    pub azimuth: f64,


    // This member is not documented.
    #[allow(missing_docs)]
    pub distance: f64,


    // This member is not documented.
    #[allow(missing_docs)]
    pub intensity: f64,

}



impl Default for LslidarPoint {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !lslidar_msgs__msg__LslidarPoint__init(&mut msg as *mut _) {
        panic!("Call to lslidar_msgs__msg__LslidarPoint__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for LslidarPoint {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPoint__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPoint__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarPoint__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for LslidarPoint {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for LslidarPoint where Self: Sized {
  const TYPE_NAME: &'static str = "lslidar_msgs/msg/LslidarPoint";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarPoint() }
  }
}


#[link(name = "lslidar_msgs__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarScan() -> *const std::ffi::c_void;
}

#[link(name = "lslidar_msgs__rosidl_generator_c")]
extern "C" {
    fn lslidar_msgs__msg__LslidarScan__init(msg: *mut LslidarScan) -> bool;
    fn lslidar_msgs__msg__LslidarScan__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<LslidarScan>, size: usize) -> bool;
    fn lslidar_msgs__msg__LslidarScan__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<LslidarScan>);
    fn lslidar_msgs__msg__LslidarScan__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<LslidarScan>, out_seq: *mut rosidl_runtime_rs::Sequence<LslidarScan>) -> bool;
}

// Corresponds to lslidar_msgs__msg__LslidarScan
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]

/// Altitude of all the points within this scan

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarScan {

    // This member is not documented.
    #[allow(missing_docs)]
    pub altitude: f64,

    /// The valid points in this scan sorted by azimuth
    /// from 0 to 359.99
    pub points: rosidl_runtime_rs::Sequence<super::super::msg::rmw::LslidarPoint>,

}



impl Default for LslidarScan {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !lslidar_msgs__msg__LslidarScan__init(&mut msg as *mut _) {
        panic!("Call to lslidar_msgs__msg__LslidarScan__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for LslidarScan {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarScan__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarScan__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarScan__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for LslidarScan {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for LslidarScan where Self: Sized {
  const TYPE_NAME: &'static str = "lslidar_msgs/msg/LslidarScan";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarScan() }
  }
}


#[link(name = "lslidar_msgs__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarSweep() -> *const std::ffi::c_void;
}

#[link(name = "lslidar_msgs__rosidl_generator_c")]
extern "C" {
    fn lslidar_msgs__msg__LslidarSweep__init(msg: *mut LslidarSweep) -> bool;
    fn lslidar_msgs__msg__LslidarSweep__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<LslidarSweep>, size: usize) -> bool;
    fn lslidar_msgs__msg__LslidarSweep__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<LslidarSweep>);
    fn lslidar_msgs__msg__LslidarSweep__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<LslidarSweep>, out_seq: *mut rosidl_runtime_rs::Sequence<LslidarSweep>) -> bool;
}

// Corresponds to lslidar_msgs__msg__LslidarSweep
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]


// This struct is not documented.
#[allow(missing_docs)]

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarSweep {

    // This member is not documented.
    #[allow(missing_docs)]
    pub header: std_msgs::msg::rmw::Header,

    /// The 0th scan is at the bottom
    pub scans: [super::super::msg::rmw::LslidarScan; 16],

}



impl Default for LslidarSweep {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !lslidar_msgs__msg__LslidarSweep__init(&mut msg as *mut _) {
        panic!("Call to lslidar_msgs__msg__LslidarSweep__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for LslidarSweep {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarSweep__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarSweep__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { lslidar_msgs__msg__LslidarSweep__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for LslidarSweep {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for LslidarSweep where Self: Sized {
  const TYPE_NAME: &'static str = "lslidar_msgs/msg/LslidarSweep";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__lslidar_msgs__msg__LslidarSweep() }
  }
}


