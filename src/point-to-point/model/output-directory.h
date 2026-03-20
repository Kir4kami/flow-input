#ifndef OUTPUT_DIRECTORY_H
#define OUTPUT_DIRECTORY_H

#include <string>

namespace ns3 {

void SetOutputDirectory (const std::string &path);
std::string GetOutputDirectory ();

} // namespace ns3

#endif /* OUTPUT_DIRECTORY_H */
