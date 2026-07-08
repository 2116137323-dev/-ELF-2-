#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};



// Corresponds to lslidar_msgs__msg__LslidarDifop

// This struct is not documented.
#[allow(missing_docs)]

#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
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
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::msg::rmw::LslidarDifop::default())
  }
}

impl rosidl_runtime_rs::Message for LslidarDifop {
  type RmwMsg = super::msg::rmw::LslidarDifop;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        temperature: msg.temperature,
        rpm: msg.rpm,
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
      temperature: msg.temperature,
      rpm: msg.rpm,
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      temperature: msg.temperature,
      rpm: msg.rpm,
    }
  }
}


// Corresponds to lslidar_msgs__msg__LslidarPacket
/// Raw Leishen LIDAR packet.

#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarPacket {
    /// packet timestamp
    pub stamp: builtin_interfaces::msg::Time,

    /// packet contents
    #[cfg_attr(feature = "serde", serde(with = "serde_big_array::BigArray"))]
    pub data: [u8; 2000],

}



impl Default for LslidarPacket {
  fn default() -> Self {
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::msg::rmw::LslidarPacket::default())
  }
}

impl rosidl_runtime_rs::Message for LslidarPacket {
  type RmwMsg = super::msg::rmw::LslidarPacket;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        stamp: builtin_interfaces::msg::Time::into_rmw_message(std::borrow::Cow::Owned(msg.stamp)).into_owned(),
        data: msg.data,
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        stamp: builtin_interfaces::msg::Time::into_rmw_message(std::borrow::Cow::Borrowed(&msg.stamp)).into_owned(),
        data: msg.data,
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      stamp: builtin_interfaces::msg::Time::from_rmw_message(msg.stamp),
      data: msg.data,
    }
  }
}


// Corresponds to lslidar_msgs__msg__LslidarPoint
/// Time when the point is captured

#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
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
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::msg::rmw::LslidarPoint::default())
  }
}

impl rosidl_runtime_rs::Message for LslidarPoint {
  type RmwMsg = super::msg::rmw::LslidarPoint;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        time: msg.time,
        x: msg.x,
        y: msg.y,
        z: msg.z,
        azimuth: msg.azimuth,
        distance: msg.distance,
        intensity: msg.intensity,
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
      time: msg.time,
      x: msg.x,
      y: msg.y,
      z: msg.z,
      azimuth: msg.azimuth,
      distance: msg.distance,
      intensity: msg.intensity,
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      time: msg.time,
      x: msg.x,
      y: msg.y,
      z: msg.z,
      azimuth: msg.azimuth,
      distance: msg.distance,
      intensity: msg.intensity,
    }
  }
}


// Corresponds to lslidar_msgs__msg__LslidarScan
/// Altitude of all the points within this scan

#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarScan {

    // This member is not documented.
    #[allow(missing_docs)]
    pub altitude: f64,

    /// The valid points in this scan sorted by azimuth
    /// from 0 to 359.99
    pub points: Vec<super::msg::LslidarPoint>,

}



impl Default for LslidarScan {
  fn default() -> Self {
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::msg::rmw::LslidarScan::default())
  }
}

impl rosidl_runtime_rs::Message for LslidarScan {
  type RmwMsg = super::msg::rmw::LslidarScan;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        altitude: msg.altitude,
        points: msg.points
          .into_iter()
          .map(|elem| super::msg::LslidarPoint::into_rmw_message(std::borrow::Cow::Owned(elem)).into_owned())
          .collect(),
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
      altitude: msg.altitude,
        points: msg.points
          .iter()
          .map(|elem| super::msg::LslidarPoint::into_rmw_message(std::borrow::Cow::Borrowed(elem)).into_owned())
          .collect(),
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      altitude: msg.altitude,
      points: msg.points
          .into_iter()
          .map(super::msg::LslidarPoint::from_rmw_message)
          .collect(),
    }
  }
}


// Corresponds to lslidar_msgs__msg__LslidarSweep

// This struct is not documented.
#[allow(missing_docs)]

#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct LslidarSweep {

    // This member is not documented.
    #[allow(missing_docs)]
    pub header: std_msgs::msg::Header,

    /// The 0th scan is at the bottom
    pub scans: [super::msg::LslidarScan; 16],

}



impl Default for LslidarSweep {
  fn default() -> Self {
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::msg::rmw::LslidarSweep::default())
  }
}

impl rosidl_runtime_rs::Message for LslidarSweep {
  type RmwMsg = super::msg::rmw::LslidarSweep;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        header: std_msgs::msg::Header::into_rmw_message(std::borrow::Cow::Owned(msg.header)).into_owned(),
        scans: msg.scans
          .map(|elem| super::msg::LslidarScan::into_rmw_message(std::borrow::Cow::Owned(elem)).into_owned()),
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        header: std_msgs::msg::Header::into_rmw_message(std::borrow::Cow::Borrowed(&msg.header)).into_owned(),
        scans: msg.scans
          .iter()
          .map(|elem| super::msg::LslidarScan::into_rmw_message(std::borrow::Cow::Borrowed(elem)).into_owned())
          .collect::<Vec<_>>()
          .try_into()
          .unwrap(),
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      header: std_msgs::msg::Header::from_rmw_message(msg.header),
      scans: msg.scans
        .map(super::msg::LslidarScan::from_rmw_message),
    }
  }
}


