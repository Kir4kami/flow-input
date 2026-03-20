#include "output-directory.h"

#include <chrono>
#include <ctime>
#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <unistd.h>

namespace ns3 {

namespace {
std::string g_outputDirectory;

std::string
BuildDatedResultDirName ()
{
  auto now = std::chrono::system_clock::now ();
  std::time_t tt = std::chrono::system_clock::to_time_t (now);
  std::tm tm = *std::localtime (&tt);
  std::ostringstream oss;
  oss << "result-" << std::put_time (&tm, "%Y%m%d");
  return oss.str ();
}

std::string
BuildDefaultOutputDirectory ()
{
  char cwd[4096];
  std::string baseDir = ".";
  if (getcwd (cwd, sizeof(cwd)) != nullptr)
    {
      baseDir = cwd;
    }
  std::filesystem::path resultDir = std::filesystem::path (baseDir) / BuildDatedResultDirName ();
  std::error_code ec;
  std::filesystem::create_directories (resultDir, ec);
  return resultDir.string ();
}
}

void
SetOutputDirectory (const std::string &path)
{
  g_outputDirectory = path;
  if (!g_outputDirectory.empty ())
    {
      std::error_code ec;
      std::filesystem::create_directories (g_outputDirectory, ec);
    }
}

std::string
GetOutputDirectory ()
{
  if (!g_outputDirectory.empty ())
    {
      return g_outputDirectory;
    }

  const char *envDir = std::getenv ("NS3_OUTPUT_DIRECTORY");
  if (envDir != nullptr && envDir[0] != '\0')
    {
      g_outputDirectory = envDir;
      std::error_code ec;
      std::filesystem::create_directories (g_outputDirectory, ec);
      return g_outputDirectory;
    }
  g_outputDirectory = BuildDefaultOutputDirectory ();
  return g_outputDirectory;
}

} // namespace ns3
